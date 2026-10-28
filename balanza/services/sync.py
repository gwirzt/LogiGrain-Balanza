"""Envío de la cola local de pesajes a la API."""
from __future__ import annotations

import logging
import threading
from dataclasses import dataclass

from ..api.cliente import ClienteLogigrain
from ..storage.db import BaseDatos

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class ResultadoSync:
    enviados: int = 0
    fallidos: int = 0
    pendientes: int = 0
    ultimo_error: str = ""


class Sincronizador:
    def __init__(self, db: BaseDatos, cliente: ClienteLogigrain):
        self.db = db
        self.cliente = cliente
        self._lock = threading.Lock()

    def ejecutar(self) -> ResultadoSync:
        """Envía los pendientes en orden. Se detiene en el primer error para no mandar
        un segundo peso antes que su primer peso."""
        if not self._lock.acquire(blocking=False):
            return self._resultado(0, 0)  # ya hay una sincronización en curso
        try:
            enviados = fallidos = 0
            for envio in self.db.envios_pendientes():
                try:
                    respuesta = self.cliente.enviar(envio.tipo, envio.payload)
                except Exception as e:  # noqa: BLE001 - cualquier falla deja el envío pendiente
                    log.warning("No se pudo enviar %s del pesaje %s: %s", envio.tipo, envio.pesaje_id, e)
                    self.db.marcar_error(envio.id, str(e))
                    fallidos += 1
                    break
                # Antes de marcarlo enviado: quien vea el envío confirmado ya encuentra el romaneo guardado.
                if isinstance(respuesta, dict) and respuesta.get("romaneo"):
                    self.db.guardar_romaneo(envio.pesaje_id, respuesta["romaneo"])
                self.db.marcar_enviado(envio.id)
                enviados += 1
            return self._resultado(enviados, fallidos)
        finally:
            self._lock.release()

    def _resultado(self, enviados: int, fallidos: int) -> ResultadoSync:
        return ResultadoSync(enviados, fallidos, self.db.contar_pendientes(), self.db.ultimo_error_envio())
