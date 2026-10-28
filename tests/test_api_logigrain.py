"""Cliente LogiGrain contra un servidor simulado (no toca la API real)."""
import json

import httpx
import pytest

from balanza.api.cliente import ClienteHttp, ErrorApi, ErrorAutenticacion
from balanza.config import ApiConfig
from balanza.credenciales import leer_env
from balanza.models import Operacion

VEHICULO = {
    "nro_ctg": 10235770572, "dominio": "AD936VY,AH885OZ", "nombre_grano": "Trigo",
    "destinatario_razon_social": "COFCO", "posicion_actual": "EN_PUERTO_CALADO", "posicion_label": "En puerto calado",
}
DETALLE = {
    **VEHICULO, "tipo_operacion": "D", "chofer_nombre": "MARTINEZ WALTER", "transportista_nombre": "TRANSPORTE CADI",
    "codigo_turno": "20261027001383", "peso_bruto_balanza": None, "peso_tara_balanza": None, "puede_pesar": True,
}
# Romaneo que devolvió LogiGrain en la prueba real del CTG 10235570674 (41.200 / 14.240).
ROMANEO = {
    "peso_bruto_kg": 41200, "peso_tara_kg": 14240, "peso_neto_kg": 26960,
    "mermas": {"fis_humedad_kg": 0, "fis_humedad_pct": 0.0, "volatil_kg": 27, "volatil_pct": 0.1,
               "rubros_kg": 270, "rubros_pct": 1.0, "total_kg": 297, "total_pct": 1.0},
    "peso_neto_final_kg": 26663, "merma_total_kg": 297,
}


class Servidor:
    """Imita las rutas de LogiGrain que usa la balanza y registra las llamadas."""

    def __init__(self):
        self.llamadas: list[tuple[str, dict]] = []
        self.tokens_validos = {"tok-1"}
        self.siguiente_token = "tok-1"
        self.posicion = "EN_PUERTO_CALADO"

    def __call__(self, request: httpx.Request) -> httpx.Response:
        ruta = request.url.path
        cuerpo = json.loads(request.content or b"{}")
        self.llamadas.append((ruta, cuerpo))
        if ruta == "/api/v1/auth/login":
            if (cuerpo["username"], cuerpo["password"]) != ("balan", "secreto"):
                return httpx.Response(401, json={"detail": "Credenciales inválidas."})
            return httpx.Response(200, json={"access_token": self.siguiente_token, "token_type": "bearer",
                                             "is_admin": False, "sectors": [], "menu": []})
        if request.headers.get("Authorization", "").removeprefix("Bearer ") not in self.tokens_validos:
            return httpx.Response(401, json={"detail": "Token inválido o expirado."})
        if ruta == "/api/v1/ports/my-ports":
            return httpx.Response(200, json={"ports": [{"id": 1, "name": "Unidad 67 Rosario"}], "total": 1})
        if ruta == "/api/v1/cpe/posicion/lista":
            vs = [VEHICULO] if cuerpo.get("posicion") == "EN_PUERTO_CALADO" else []
            return httpx.Response(200, json={"total": len(vs), "vehiculos": vs})
        if ruta == "/api/v1/cpe/get-para-pesaje":
            if self.posicion == "FINALIZADO":
                return httpx.Response(422, json={"detail": "está en posición FINALIZADO (Finalizado)."})
            return httpx.Response(200, json={**DETALLE, "posicion_actual": self.posicion})
        if ruta == "/api/v1/balanza/registrar-peso":
            segundo = self.posicion == "CON_PRIMER_PESO"
            self.posicion = "FINALIZADO" if segundo else "CON_PRIMER_PESO"
            respuesta = {"success": True, "nro_ctg": cuerpo["nro_ctg"], "tipo_peso": "TARA" if segundo else "BRUTO",
                         "peso_registrado_kg": cuerpo["peso_kg"], "es_segundo_peso": segundo,
                         "posicion_actual": self.posicion}
            if segundo:  # como LogiGrain: el 2° peso devuelve el romaneo
                respuesta["romaneo"] = ROMANEO
            return httpx.Response(200, json=respuesta)
        return httpx.Response(404, json={"detail": "Not Found"})

    def rutas(self, ruta):
        return [c for r, c in self.llamadas if r == ruta]


@pytest.fixture
def servidor():
    return Servidor()


def cliente(servidor, **cfg):
    c = ClienteHttp(ApiConfig(modo="http", url_base="http://logigrain", **cfg), transport=httpx.MockTransport(servidor))
    c.login("balan", "secreto")
    return c


def test_login_elige_puerto(servidor):
    c = cliente(servidor)
    assert (c.port_id, c.puerto, c.usuario) == (1, "Unidad 67 Rosario", "balan")


def test_login_rechazado(servidor):
    c = ClienteHttp(ApiConfig(modo="http", url_base="http://logigrain"), transport=httpx.MockTransport(servidor))
    with pytest.raises(ErrorAutenticacion, match="Credenciales inválidas"):
        c.login("balan", "mal")


def test_login_puerto_sin_acceso(servidor):
    with pytest.raises(ErrorAutenticacion, match="puerto 9"):
        cliente(servidor, port_id=9)


def test_consultar_ctg(servidor):
    c = cliente(servidor)
    cam = c.consultar_ctg(" 10235770572 ")
    assert (cam.id, cam.patente, cam.patente_acoplado, cam.producto) == ("10235770572", "AD936VY", "AH885OZ", "Trigo")
    assert cam.operacion is Operacion.DESCARGA and cam.chofer == "MARTINEZ WALTER"
    assert servidor.rutas("/api/v1/cpe/get-para-pesaje")[-1] == {"nro_ctg": 10235770572, "port_id": 1}


def test_ctg_no_numerico(servidor):
    with pytest.raises(ErrorApi, match="solo números"):
        cliente(servidor).consultar_ctg("ABC")


def test_reloguea_si_vence_el_token(servidor):
    c = cliente(servidor)
    servidor.tokens_validos = {"tok-2"}
    servidor.siguiente_token = "tok-2"
    assert c.consultar_ctg("10235770572")
    assert len(servidor.rutas("/api/v1/auth/login")) == 2


def test_error_de_validacion_muestra_detalle(servidor):
    c = cliente(servidor)
    servidor.posicion = "FINALIZADO"
    with pytest.raises(ErrorApi, match="FINALIZADO"):
        c.consultar_ctg("10235770572")


PAYLOAD_1 = {"camion_id": "10235770572", "peso1_kg": 45320.0, "peso2_kg": None, "balanza_nro": 1}
PAYLOAD_2 = {"camion_id": "10235770572", "peso1_kg": 45320.0, "peso2_kg": 15140.0, "balanza_nro": 2}


def test_envio_deshabilitado_no_registra(servidor):
    c = cliente(servidor)
    assert c.enviar("primer_peso", PAYLOAD_1) is None
    assert servidor.rutas("/api/v1/balanza/registrar-peso") == []


def test_envio_habilitado_registra_ambos_pesos(servidor):
    c = cliente(servidor, enviar_pesos=True)
    r1 = c.enviar("primer_peso", PAYLOAD_1)
    r2 = c.enviar("segundo_peso", PAYLOAD_2)
    assert r1["tipo_peso"] == "BRUTO" and "romaneo" not in r1
    assert r2["tipo_peso"] == "TARA" and r2["romaneo"]["peso_neto_final_kg"] == 26_663
    assert servidor.rutas("/api/v1/balanza/registrar-peso") == [
        {"port_id": 1, "nro_ctg": 10235770572, "peso_kg": 45320, "balanza_nro": 1},
        {"port_id": 1, "nro_ctg": 10235770572, "peso_kg": 15140, "balanza_nro": 2},
    ]


def test_reintento_no_duplica_pesos(servidor):
    """Si la respuesta se perdió pero la API ya registró el peso, el reintento no lo vuelve a mandar."""
    c = cliente(servidor, enviar_pesos=True)
    servidor.posicion = "CON_PRIMER_PESO"
    c.enviar("primer_peso", PAYLOAD_1)
    servidor.posicion = "FINALIZADO"
    assert c.enviar("segundo_peso", PAYLOAD_2) is None  # el romaneo se perdió con la respuesta original
    assert servidor.rutas("/api/v1/balanza/registrar-peso") == []


def test_leer_env(tmp_path):
    ruta = tmp_path / ".env"
    ruta.write_text('# comentario\nUSUARIO_LOGIGRAIN=balan\r\nCONTRASENA_LOGIGRAIN="a=b c"\n', encoding="utf-8")
    assert leer_env(ruta) == {"USUARIO_LOGIGRAIN": "balan", "CONTRASENA_LOGIGRAIN": "a=b c"}
    assert leer_env(tmp_path / "no-existe") == {}
