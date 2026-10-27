from datetime import datetime, timedelta

import pytest

from balanza.api.mock import ClienteMock
from balanza.config import TicketConfig, cargar_config
from balanza.models import Camion, EstadoPesaje, LecturaPeso, Operacion
from balanza.printing.ticket import html_ticket
from balanza.scale.ciclo import CicloBalanza
from balanza.scale.estabilidad import DetectorEstabilidad
from balanza.scale.fuentes import FuenteSimulada
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


def test_simulador_genera_lineas_parseables():
    fuente = FuenteSimulada(intervalo_s=0, semilla=1)
    fuente.abrir()
    pesos = [ParserGenerico().parsear(fuente.leer_linea()).kg for _ in range(300)]
    assert min(pesos) == 0 and max(pesos) > 10_000
    assert all(kg % 20 == 0 for kg in pesos)  # división de 20 kg


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
    html = html_ticket(p, TicketConfig(empresa="Logiports"))
    assert "AB123CD" in html and "30.000 kg" in html and "BAL-1-000001" in html


def _config(tmp_path, texto):
    ruta = tmp_path / "c.toml"
    ruta.write_text(texto, encoding="utf-8")
    return cargar_config(ruta)


def test_config_por_defecto_y_formato_anterior(tmp_path):
    cfg = cargar_config(None)
    assert [(b.nro, b.modo) for b in cfg.balanzas] == [(1, "simulador")]
    cfg = _config(tmp_path, 'puesto = "B2"\n[balanza]\nmodo = "serie"\npuerto = "COM3"\n')
    assert (cfg.puesto, cfg.balanzas[0].modo, cfg.balanzas[0].puerto, cfg.api.modo) == ("B2", "serie", "COM3", "mock")


def test_config_dos_balanzas(tmp_path):
    cfg = _config(tmp_path, '[[balanzas]]\nnro = 1\npuerto = "COM3"\n[[balanzas]]\nnro = 2\npuerto = "COM4"\n')
    assert [(b.nro, b.puerto) for b in cfg.balanzas] == [(1, "COM3"), (2, "COM4")]


@pytest.mark.parametrize("texto, mensaje", [
    ("[balanza]\npuerta = 'COM3'\n", "puerta"),
    ("[[balanzas]]\nnro = 1\n[[balanzas]]\nnro = 1\n", "nro distinto"),
    ("[[balanzas]]\nnro = 1\n[[balanzas]]\nnro = 2\n[[balanzas]]\nnro = 3\n", "1 o 2"),
    ("[api]\nbalanza_nro = 1\n", "balanza_nro ya no va"),
])
def test_config_errores(tmp_path, texto, mensaje):
    with pytest.raises(ValueError, match=mensaje):
        _config(tmp_path, texto)


def test_config_toml_mal_escrito(tmp_path):
    import tomllib
    with pytest.raises(tomllib.TOMLDecodeError):
        _config(tmp_path, "[api]\nbalanza_nro = 1\nbalanza_nro = 2\n")  # clave repetida


def test_registra_la_balanza_de_cada_peso(servicio, db):
    servicio.capturar(CAMION, lectura(45_000), balanza_nro=1)
    p = servicio.capturar(CAMION, lectura(15_000), balanza_nro=2)
    assert (p.balanza1_nro, p.balanza2_nro) == (1, 2)
    assert [e.payload["balanza_nro"] for e in db.envios_pendientes()] == [1, 2]
    assert "1° peso (B1)" in html_ticket(p, TicketConfig()) and "2° peso (B2)" in html_ticket(p, TicketConfig())
