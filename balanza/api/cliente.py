"""Cliente de la API de LogiGrain."""
from __future__ import annotations

import logging
import threading
from abc import ABC, abstractmethod
from datetime import datetime

import httpx

from ..config import ApiConfig
from ..models import Camion, Operacion

log = logging.getLogger(__name__)


class ErrorApi(Exception):
    def __init__(self, mensaje: str, status: int | None = None):
        super().__init__(mensaje)
        self.status = status


class ErrorAutenticacion(ErrorApi):
    pass


class ClienteLogigrain(ABC):
    requiere_login = False
    usuario = ""
    puerto = ""

    def login(self, usuario: str, contrasena: str) -> None:
        """Valida las credenciales y elige el puerto. Lanza ErrorAutenticacion si no son válidas."""

    @abstractmethod
    def consultar_ctg(self, ctg: str) -> Camion:
        """Datos de la Carta de Porte, validando que se pueda pesar (lanza ErrorApi si no)."""

    @abstractmethod
    def enviar(self, tipo: str, payload: dict) -> dict | None:
        """Informa un evento de pesaje. Debe lanzar excepción si la API no lo aceptó.
        Devuelve la respuesta de la API (en el 2° peso trae el `romaneo`), o None si no se envió."""


def _detalle_error(r: httpx.Response) -> str:
    try:
        detalle = r.json().get("detail")
    except ValueError:
        return r.text[:300]
    if isinstance(detalle, list):  # errores de validación de FastAPI
        return "; ".join(str(d.get("msg", d)) for d in detalle)
    return str(detalle or r.text[:300])


def _fecha(valor) -> datetime | None:
    try:
        return datetime.fromisoformat(valor) if valor else None
    except ValueError:
        return None


class ClienteHttp(ClienteLogigrain):
    requiere_login = True

    def __init__(self, cfg: ApiConfig, transport: httpx.BaseTransport | None = None):
        self.cfg = cfg
        self.port_id = cfg.port_id
        self._http = httpx.Client(
            base_url=cfg.url_base.rstrip("/"), timeout=cfg.timeout_s, transport=transport,
            headers={"Accept": "application/json"},
        )
        self._credenciales: tuple[str, str] | None = None
        self._lock = threading.Lock()

    # --- Sesión ----------------------------------------------------------------

    def login(self, usuario: str, contrasena: str) -> None:
        self._autenticar(usuario, contrasena)
        self._credenciales = (usuario, contrasena)
        self.usuario = usuario
        puertos = self._post("/api/v1/ports/my-ports", {}).get("ports") or []
        if not puertos:
            raise ErrorAutenticacion("El usuario no tiene puertos asignados en LogiGrain.")
        if self.port_id is None:
            elegido = puertos[0]
        else:
            elegido = next((p for p in puertos if p.get("id") == self.port_id), None)
            if elegido is None:
                raise ErrorAutenticacion(f"El usuario no tiene acceso al puerto {self.port_id}.")
        self.port_id = elegido["id"]
        self.puerto = elegido.get("name") or str(self.port_id)
        log.info("Sesión iniciada en LogiGrain: usuario %s, puerto %s (%s)", usuario, self.puerto, self.port_id)

    def _autenticar(self, usuario: str, contrasena: str) -> None:
        try:
            r = self._http.post("/api/v1/auth/login", json={"username": usuario, "password": contrasena})
        except httpx.HTTPError as e:
            raise ErrorApi(f"No se pudo conectar con LogiGrain ({self.cfg.url_base}): {e}") from e
        if r.status_code in (401, 403):
            raise ErrorAutenticacion(_detalle_error(r) or "Usuario o contraseña incorrectos.", r.status_code)
        if r.status_code >= 400:
            raise ErrorApi(f"Error al iniciar sesión ({r.status_code}): {_detalle_error(r)}", r.status_code)
        self._http.headers["Authorization"] = f"Bearer {r.json()['access_token']}"

    def _post(self, ruta: str, cuerpo: dict, reintentar: bool = True) -> dict:
        try:
            r = self._http.post(ruta, json=cuerpo)
        except httpx.HTTPError as e:
            raise ErrorApi(f"Sin conexión con LogiGrain: {e}") from e
        if r.status_code == 401 and reintentar and self._credenciales:
            log.info("Token vencido, se inicia sesión de nuevo.")
            with self._lock:
                self._autenticar(*self._credenciales)
            return self._post(ruta, cuerpo, reintentar=False)
        if r.status_code >= 400:
            raise ErrorApi(_detalle_error(r), r.status_code)
        return r.json()

    # --- Cartas de Porte ---------------------------------------------------------

    def consultar_ctg(self, ctg: str) -> Camion:
        datos = self._post("/api/v1/cpe/get-para-pesaje", {"nro_ctg": validar_ctg(ctg), "port_id": self.port_id})
        return camion_desde_detalle(datos)

    # --- Pesos -----------------------------------------------------------------

    def enviar(self, tipo: str, payload: dict) -> dict | None:
        nro_ctg = int(payload["camion_id"])
        peso = payload["peso1_kg"] if tipo == "primer_peso" else payload["peso2_kg"]
        if not self.cfg.enviar_pesos:
            log.warning("Envío deshabilitado (enviar_pesos = false): no se registra %s de %s kg en el CTG %s.",
                        tipo, peso, nro_ctg)
            return None
        if self._ya_registrado(tipo, nro_ctg):
            log.warning("El %s del CTG %s ya figura en LogiGrain: no se reenvía.", tipo, nro_ctg)
            return None
        cuerpo = {"port_id": self.port_id, "nro_ctg": nro_ctg, "peso_kg": int(round(peso))}
        if payload.get("balanza_nro") is not None:
            cuerpo["balanza_nro"] = payload["balanza_nro"]
        respuesta = self._post("/api/v1/balanza/registrar-peso", cuerpo)
        log.info("Registrado en LogiGrain: %s de %s kg, CTG %s, balanza %s.",
                 tipo, cuerpo["peso_kg"], nro_ctg, cuerpo.get("balanza_nro"))
        return respuesta

    def _ya_registrado(self, tipo: str, nro_ctg: int) -> bool:
        """La API decide sola si un peso es el 1° o el 2°. Si un envío anterior llegó pero se cortó la
        respuesta, reenviarlo registraría un peso de más; por eso se consulta la posición antes."""
        try:
            datos = self._post("/api/v1/cpe/get-para-pesaje", {"nro_ctg": nro_ctg, "port_id": self.port_id})
        except ErrorApi as e:
            if tipo == "segundo_peso" and "FINALIZADO" in str(e):
                return True
            raise
        return tipo == "primer_peso" and datos.get("posicion_actual") == "CON_PRIMER_PESO"


def validar_ctg(ctg: str) -> int:
    ctg = ctg.strip().replace(" ", "").replace("-", "")
    if not ctg.isdigit():
        raise ErrorApi("El CTG debe tener solo números.")
    return int(ctg)


def _dominios(texto: str | None) -> list[str]:
    return [d.strip() for d in (texto or "").split(",") if d.strip()]


def camion_desde_lista(v: dict) -> Camion:
    dominios = _dominios(v.get("dominio"))
    return Camion(
        id=str(v["nro_ctg"]),
        patente=dominios[0] if dominios else "",
        patente_acoplado=", ".join(dominios[1:]),
        producto=v.get("nombre_grano") or "",
        destinatario=v.get("destinatario_razon_social") or "",
        posicion=v.get("posicion_actual") or "",
        posicion_label=v.get("posicion_label") or "",
        datos=v,
    )


def camion_desde_detalle(d: dict) -> Camion:
    camion = camion_desde_lista(d)
    camion.operacion = Operacion.CARGA if d.get("tipo_operacion") == "C" else Operacion.DESCARGA
    camion.chofer = d.get("chofer_nombre") or ""
    camion.transportista = d.get("transportista_nombre") or ""
    camion.turno = d.get("codigo_turno") or ""
    camion.chofer_cuit = str(d.get("cuit_chofer") or "")
    camion.fecha_ingreso = _fecha(d.get("pos_fecha_llegada_puerto"))
    camion.cpe_id = d.get("id")
    camion.grado = "" if d.get("calada_grado") is None else str(d["calada_grado"])
    # 1° peso de balanza: en descarga es el bruto (entra lleno), en carga la tara (entra vacío).
    if camion.operacion is Operacion.DESCARGA:
        camion.primer_peso_kg = d.get("peso_bruto_balanza")
        camion.primer_peso_momento = _fecha(d.get("pos_fecha_peso_bruto"))
        camion.primer_peso_balanza_nro = d.get("balanza_nro_bruto")
    else:
        camion.primer_peso_kg = d.get("peso_tara_balanza")
        camion.primer_peso_momento = _fecha(d.get("pos_fecha_peso_tara"))
        camion.primer_peso_balanza_nro = d.get("balanza_nro_tara")
    return camion
