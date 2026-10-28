from datetime import datetime, timedelta

import pytest

from balanza.api.mock import ClienteMock
from balanza.config import TicketConfig, cargar_config
from balanza.ficha import proximo_paso
from balanza.models import Camion, EstadoPesaje, LecturaPeso, Operacion
from balanza.printing.ticket import _digito_luhn, codigo_validacion, guardar_pdf, lineas_ticket, ruta_pdf
from balanza.scale.ciclo import CicloBalanza
from balanza.scale.estabilidad import DetectorEstabilidad
from balanza.scale.fuentes import RANGO_BRUTO, RANGO_TARA, FuenteSimulada
from balanza.scale.parsers import ParserGenerico
from balanza.services.pesaje import ErrorPesaje, ServicioPesaje
from balanza.services.sync import Sincronizador
from balanza.storage.db import BaseDatos

CAMION = Camion(id="T-1", patente="AB123CD", producto="Soja", operacion=Operacion.DESCARGA)


def lectura(kg, estable=True, hace_s=0):
    return LecturaPeso(kg, estable, f"ST,GS,{kg:+07.0f}kg", datetime.now() - timedelta(seconds=hace_s))


@pytest.fixture
def db(tmp_path):
    return BaseDatos(tmp_path / "test.db")


@pytest.fixture
def servicio(db):
    return ServicioPesaje(db, "BAL-1", peso_minimo_kg=500)


# --- Parser y estabilidad ------------------------------------------------------

@pytest.mark.parametrize("linea, kg, estable", [
    ("ST,GS,+045320kg", 45320, True),
    ("US,GS,+012000kg", 12000, False),
    (" 045320 kg", 45320, None),
    ("-00150", -150, None),
    ("12,5", 12.5, None),
])
def test_parser_generico(linea, kg, estable):
    r = ParserGenerico().parsear(linea)
    assert r.kg == kg and r.estable is estable


def test_parser_ignora_basura():
    assert ParserGenerico().parsear("ERR") is None


def test_detector_estabilidad():
    d = DetectorEstabilidad(lecturas=3, tolerancia_kg=20)
    assert not d.agregar(1000)
    assert not d.agregar(1010)
    assert d.agregar(1000)
    assert not d.agregar(1100)


def test_despues_de_pesar_queda_en_cero_hasta_que_baja_el_camion():
    ciclo = CicloBalanza(umbral_cero_kg=100)
    assert ciclo.filtrar(lectura(45_000)).kg == 45_000
    ciclo.pesado()
    for kg in (45_000, 45_020, 20_000, 120):  # el camión sigue arriba o bajando
        mostrada = ciclo.filtrar(lectura(kg))
        assert (mostrada.kg, mostrada.estable) == (0, False)
    assert ciclo.filtrar(lectura(100)).kg == 100  # bajó: vuelve a leer
    assert ciclo.filtrar(lectura(30_000, estable=False)).kg == 30_000  # sube el próximo
    assert ciclo.filtrar(lectura(46_000)).estable


def _leer(fuente, n):
    return [ParserGenerico().parsear(fuente.leer_linea()) for _ in range(n)]


def test_simulador_vacio_hasta_que_sube_un_camion():
    fuente = FuenteSimulada(intervalo_s=0, semilla=1)
    fuente.abrir()
    assert all((r.kg, r.estable) == (0, True) for r in _leer(fuente, 50))


@pytest.mark.parametrize("tipo, rango", [("TARA", RANGO_TARA), ("BRUTO", RANGO_BRUTO)])
def test_simulador_sube_con_peso_de_tara_o_bruto(tipo, rango):
    for semilla in range(20):
        fuente = FuenteSimulada(intervalo_s=0, semilla=semilla)
        fuente.abrir()
        fuente.subir(tipo)
        lecturas = _leer(fuente, 100)
        assert all(r.kg % 20 == 0 for r in lecturas)  # división de 20 kg
        estables = [r.kg for r in lecturas if r.estable]
        assert len(estables) > 70 and all(rango[0] <= kg <= rango[1] for kg in estables)


def test_simulador_baja_despues_de_pesar_y_sube_el_proximo():
    fuente = FuenteSimulada(intervalo_s=0, semilla=1)
    fuente.abrir()
    fuente.subir("BRUTO")
    _leer(fuente, 50)
    fuente.bajar()
    assert all((r.kg, r.estable) == (0, True) for r in _leer(fuente, 50)[-30:])

    fuente.subir("BRUTO")
    _leer(fuente, 50)
    fuente.subir("TARA")  # otro camión sin haber pesado: baja el anterior y sube el nuevo
    lecturas = _leer(fuente, 80)
    assert any(r.kg <= 100 for r in lecturas)
    assert RANGO_TARA[0] <= lecturas[-1].kg <= RANGO_TARA[1] and lecturas[-1].estable


def test_api_de_prueba_carga_informa_la_tara_como_primer_peso():
    cliente = ClienteMock()
    ctg =next(str(n) for n in range(1, 100) if ClienteMock().consultar_ctg(str(n)).operacion is Operacion.CARGA)
    camion = cliente.consultar_ctg(ctg)
    assert proximo_paso(camion) == (1, "TARA")
    cliente.enviar("primer_peso", {"camion_id": ctg, "peso1_kg": 14_000, "balanza_nro": 2,
                                   "peso1_momento": "2026-10-27T10:00:00"})
    camion = cliente.consultar_ctg(ctg)
    assert proximo_paso(camion) == (2, "BRUTO")
    assert (camion.primer_peso_kg, camion.primer_peso_balanza_nro) == (14_000, 2)


# --- Captura de pesos ----------------------------------------------------------

def test_ciclo_completo_descarga(servicio, db):
    p1 = servicio.capturar(CAMION, lectura(45_000))
    assert p1.estado is EstadoPesaje.ABIERTO and p1.id is not None

    p2 = servicio.capturar(CAMION, lectura(15_000))
    assert p2.id == p1.id and p2.estado is EstadoPesaje.CERRADO
    assert (p2.bruto_kg, p2.tara_kg, p2.neto_kg) == (45_000, 15_000, 30_000)
    assert db.pesaje_abierto(CAMION.id) is None
    assert [e.tipo for e in db.envios_pendientes()] == ["primer_peso", "segundo_peso"]


def test_primer_peso_tomado_en_otra_balanza(servicio, db):
    camion = Camion(id="T-3", patente="AA111BB", operacion=Operacion.DESCARGA, posicion="CON_PRIMER_PESO",
                    primer_peso_kg=44_000, primer_peso_momento=datetime.now())
    p = servicio.capturar(camion, lectura(14_000))
    assert p.estado is EstadoPesaje.CERRADO and p.neto_kg == 30_000
    assert [e.tipo for e in db.envios_pendientes()] == ["segundo_peso"]  # el 1° no se reenvía


def test_carga_entra_vacio(servicio):
    camion = Camion(id="T-2", patente="AE789GH", operacion=Operacion.CARGA)
    servicio.capturar(camion, lectura(15_000))
    p = servicio.capturar(camion, lectura(46_000))
    assert p.neto_kg == 31_000


@pytest.mark.parametrize("lect, mensaje", [
    (None, "No hay lectura"),
    (lectura(45_000, estable=False), "no está estable"),
    (lectura(100), "menor al mínimo"),
    (lectura(45_000, hace_s=10), "desactualizada"),
])
def test_validaciones(servicio, db, lect, mensaje):
    with pytest.raises(ErrorPesaje, match=mensaje):
        servicio.capturar(CAMION, lect)
    assert db.contar_pendientes() == 0


# --- Sincronización ------------------------------------------------------------

class ClienteQueFalla(ClienteMock):
    def __init__(self, fallar_desde):
        super().__init__()
        self.fallar_desde = fallar_desde

    def enviar(self, tipo, payload):
        if len(self.enviados) >= self.fallar_desde:
            raise ConnectionError("sin conexión")
        super().enviar(tipo, payload)


def test_sync_envia_en_orden_y_reintenta(servicio, db):
    servicio.capturar(CAMION, lectura(45_000))
    servicio.capturar(CAMION, lectura(15_000))

    cliente = ClienteQueFalla(fallar_desde=1)
    r = Sincronizador(db, cliente).ejecutar()
    assert (r.enviados, r.fallidos, r.pendientes) == (1, 1, 1)
    assert "sin conexión" in r.ultimo_error

    cliente.fallar_desde = 99
    r = Sincronizador(db, cliente).ejecutar()
    assert (r.enviados, r.pendientes) == (1, 0)
    assert [t for t, _ in cliente.enviados] == ["primer_peso", "segundo_peso"]
    assert cliente.enviados[1][1]["neto_kg"] == 30_000


# --- Ticket y configuración ----------------------------------------------------

def test_ticket(servicio):
    servicio.capturar(CAMION, lectura(45_000))
    p = servicio.capturar(CAMION, lectura(15_000))
    lineas = lineas_ticket(p, TicketConfig(empresa="Logiports"))
    assert lineas[0] == "LOGIPORTS" and "Patente : AB123CD" in lineas and "Desc.: 30000 Kg." in lineas


def _config(tmp_path, texto):
    ruta = tmp_path / "c.toml"
    ruta.write_text(texto, encoding="utf-8")
    return cargar_config(ruta)


def test_config_por_defecto_y_formato_anterior(tmp_path):
    cfg = cargar_config(None)
    assert [(b.nro, b.modo) for b in cfg.balanzas] == [(1, "simulador")]
    cfg = _config(tmp_path, 'puesto = "B2"\n[balanza]\nmodo = "serie"\npuerto = "COM3"\n')
    assert (cfg.puesto, cfg.balanzas[0].modo, cfg.balanzas[0].puerto, cfg.api.modo) == ("B2", "serie", "COM3", "mock")


@pytest.mark.parametrize("api, permitido", [
    ('modo = "mock"\nenviar_pesos = true', True),
    ('modo = "http"\nenviar_pesos = false', True),
    ('modo = "http"\nenviar_pesos = true', False),
    ('modo = "http"\nenviar_pesos = true\npermitir_pesos_simulados = true', True),
])
def test_simulador_permitido(tmp_path, api, permitido):
    assert _config(tmp_path, f"[api]\n{api}\n").api.simulador_permitido is permitido


def test_config_dos_balanzas(tmp_path):
    cfg = _config(tmp_path, '[[balanzas]]\nnro = 1\npuerto = "COM3"\n[[balanzas]]\nnro = 2\npuerto = "COM4"\n')
    assert [(b.nro, b.puerto) for b in cfg.balanzas] == [(1, "COM3"), (2, "COM4")]


@pytest.mark.parametrize("texto, mensaje", [
    ("[balanza]\npuerta = 'COM3'\n", "puerta"),
    ("[[balanzas]]\nnro = 1\n[[balanzas]]\nnro = 1\n", "nro distinto"),
    ("[[balanzas]]\nnro = 1\n[[balanzas]]\nnro = 2\n[[balanzas]]\nnro = 3\n", "1 o 2"),
    ("[api]\nbalanza_nro = 1\n", "balanza_nro ya no va"),
    ("[[balanzas]]\nmodo = 'simulado'\n", "Modo de balanza desconocido"),
])
def test_config_errores(tmp_path, texto, mensaje):
    with pytest.raises(ValueError, match=mensaje):
        _config(tmp_path, texto)


def test_punto_de_entrada_importa():
    import balanza.__main__  # noqa: F401 - el .exe arranca desde acá


def test_config_toml_mal_escrito(tmp_path):
    import tomllib
    with pytest.raises(tomllib.TOMLDecodeError):
        _config(tmp_path, "[api]\nbalanza_nro = 1\nbalanza_nro = 2\n")  # clave repetida


def test_registra_la_balanza_de_cada_peso(servicio, db):
    servicio.capturar(CAMION, lectura(45_000), balanza_nro=1)
    p = servicio.capturar(CAMION, lectura(15_000), balanza_nro=2)
    assert (p.balanza1_nro, p.balanza2_nro) == (1, 2)
    assert [e.payload["balanza_nro"] for e in db.envios_pendientes()] == [1, 2]
    assert "Balanza       : 2 Modo Automatico" in lineas_ticket(p, TicketConfig())


# --- Romaneo de LogiGrain y PDF del ticket ---------------------------------------

ROMANEO = {
    "peso_bruto_kg": 41200, "peso_tara_kg": 14240, "peso_neto_kg": 26960,
    "mermas": {"fis_humedad_kg": 0, "fis_humedad_pct": 0.0, "volatil_kg": 27, "volatil_pct": 0.1,
               "rubros_kg": 270, "rubros_pct": 1.0, "total_kg": 297, "total_pct": 1.0},
    "peso_neto_final_kg": 26663, "merma_total_kg": 297,
}


def test_sync_guarda_el_romaneo_del_segundo_peso(servicio, db):
    servicio.capturar(CAMION, lectura(45_000))
    p = servicio.capturar(CAMION, lectura(15_000))
    assert db.envio_pendiente(p.id, "segundo_peso")
    Sincronizador(db, ClienteMock()).ejecutar()
    assert not db.envio_pendiente(p.id, "segundo_peso")
    guardado = db.obtener_pesaje(p.id)
    assert guardado.romaneo["peso_neto_kg"] == 30_000 and guardado.romaneo["peso_neto_final_kg"] < 30_000


def test_sin_conexion_queda_pendiente_y_sin_romaneo(servicio, db):
    servicio.capturar(CAMION, lectura(45_000))
    p = servicio.capturar(CAMION, lectura(15_000))
    Sincronizador(db, ClienteQueFalla(fallar_desde=1)).ejecutar()
    assert db.envio_pendiente(p.id, "segundo_peso") and db.obtener_pesaje(p.id).romaneo is None


def test_migracion_agrega_columna_romaneo(tmp_path):
    import sqlite3
    ruta = tmp_path / "vieja.db"
    with sqlite3.connect(ruta) as cx:  # base de una versión anterior, sin la columna romaneo
        cx.execute("""CREATE TABLE pesajes (id INTEGER PRIMARY KEY AUTOINCREMENT, camion_id TEXT NOT NULL,
                      patente TEXT NOT NULL, patente_acoplado TEXT NOT NULL DEFAULT '', operacion TEXT NOT NULL,
                      puesto TEXT NOT NULL, producto TEXT NOT NULL DEFAULT '', chofer TEXT NOT NULL DEFAULT '',
                      transportista TEXT NOT NULL DEFAULT '', peso1_kg REAL NOT NULL, peso1_momento TEXT NOT NULL,
                      peso1_crudo TEXT NOT NULL DEFAULT '', peso2_kg REAL, peso2_momento TEXT,
                      peso2_crudo TEXT NOT NULL DEFAULT '')""")
    db = BaseDatos(ruta)
    p = ServicioPesaje(db, "BAL-1", 500).capturar(CAMION, lectura(45_000))
    db.guardar_romaneo(p.id, ROMANEO)
    assert db.obtener_pesaje(p.id).romaneo == ROMANEO


def _pesaje_cerrado(servicio, romaneo=None):
    servicio.capturar(CAMION, lectura(41_200))
    p = servicio.capturar(CAMION, lectura(14_240))
    p.romaneo = romaneo
    return p


CPE_TICKET = Camion(
    id="10235570674", patente="HDD168", producto="Soja", operacion=Operacion.DESCARGA,
    chofer="CERPA WALTER", chofer_cuit="20220592627", fecha_ingreso=datetime(2026, 10, 27, 8, 39, 4),
    cpe_id=94, grado="0",
)


def test_ticket_con_el_formato_del_puerto(db):
    servicio = ServicioPesaje(db, "BALANZA-1", 500, operador="ucastellan")
    servicio.capturar(CPE_TICKET, lectura(41_200), balanza_nro=1)
    p = servicio.capturar(CPE_TICKET, lectura(14_240), balanza_nro=1)
    p.romaneo = ROMANEO
    lineas = lineas_ticket(p, TicketConfig(empresa="Servicios Portuarios S. A."))
    esperado = [
        "SERVICIOS PORTUARIOS S. A.",
        "Chofer : CERPA WALTER",
        "Cuit   : 20220592627",
        "Ingreso : 27/10/2026 08:39:04",
        f"Salio   : {p.peso2_momento:%d/%m/%Y %H:%M:%S}",
        "Operador : ucastellan",
        "C. P.: 10235570674   Código : 94",
        "Patente : HDD168",
        "Producto : Soja",
        "Bruto: 41200 Kg.",
        "Tara : 14240 Kg.",
        "Desc.: 26960 Kg.",
        "Mermas   : 297 Kg.",
        "F. EST-  : 270 Kg.",
        "Neto : 26663 Kg.",
        "Balanza       : 1 Modo Automatico",
        "Liq:Grado 0",
        "Merma Total :1.10",
    ]
    assert [linea for linea in lineas if linea in esperado] == esperado  # todas, en este orden
    assert lineas[-1] == f"Validación: {codigo_validacion(p)}"


def test_ticket_sin_romaneo(servicio):
    lineas = lineas_ticket(_pesaje_cerrado(servicio), TicketConfig())
    assert "Desc.: 26960 Kg." in lineas and "Mermas   : pendiente (sin romaneo de LogiGrain)" in lineas
    assert not any(linea.startswith(("Neto", "F. EST", "Merma Total")) for linea in lineas)


def test_ticket_carga_y_simulador(db):
    camion = Camion(id="T-9", patente="AA111BB", operacion=Operacion.CARGA)
    servicio = ServicioPesaje(db, "BAL-1", 500)
    p1 = servicio.capturar(camion, lectura(14_000), balanza_nro=1, simulado=True)
    assert "COMPROBANTE DE 1° PESAJE" in lineas_ticket(p1, TicketConfig())
    assert "Tara: 14000 Kg." in lineas_ticket(p1, TicketConfig())  # carga: el 1° peso es la tara
    p2 = servicio.capturar(camion, lectura(45_000), balanza_nro=2)
    lineas = lineas_ticket(p2, TicketConfig())
    assert "Carg.: 31000 Kg." in lineas and "Balanza       : 2 Modo Simulador" in lineas


def test_chofer_sin_nombre_no_repite_el_cuit(db):
    camion = Camion(id="T-8", patente="AA", chofer="CUIT 20266609036", chofer_cuit="20266609036")
    p = ServicioPesaje(db, "BAL-1", 500).capturar(camion, lectura(41_200))
    assert "Chofer : " in lineas_ticket(p, TicketConfig()) and "Cuit   : 20266609036" in lineas_ticket(p, TicketConfig())


def test_codigo_de_validacion(servicio):
    p = _pesaje_cerrado(servicio)
    codigo = codigo_validacion(p)
    assert len(codigo) == 13 and codigo.isdigit()
    assert codigo[-1] == _digito_luhn(codigo[:-1])
    assert codigo_validacion(p) == codigo  # se puede recalcular
    p.romaneo = ROMANEO
    assert codigo_validacion(p) == codigo  # no cambia cuando llega el romaneo
    p.peso2_kg = 14_000
    assert codigo_validacion(p) != codigo  # si se altera un peso, ya no coincide


def test_ruta_del_pdf(servicio):
    p1 = servicio.capturar(CAMION, lectura(41_200))
    assert ruta_pdf(p1, "tickets").name == f"BAL-1-000001_CTG{CAMION.id}_1er_peso.pdf"
    p2 = servicio.capturar(CAMION, lectura(14_240))
    ruta = ruta_pdf(p2, "tickets")
    assert ruta.name == f"BAL-1-000001_CTG{CAMION.id}.pdf" and ruta.parent.name == f"{p2.peso2_momento:%Y-%m}"


def test_guardar_pdf(servicio, tmp_path, monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("QT_QPA_FONTDIR", "C:/Windows/Fonts")
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])  # noqa: F841 - Qt necesita la aplicación creada
    ruta = guardar_pdf(_pesaje_cerrado(servicio, ROMANEO), TicketConfig(), tmp_path / "tickets")
    assert ruta.exists() and ruta.read_bytes().startswith(b"%PDF")
