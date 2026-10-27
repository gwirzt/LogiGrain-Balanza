"""Ejecución en segundo plano (llamadas a la API) para no congelar la pantalla."""
from __future__ import annotations

import logging

from PySide6.QtCore import QObject, QRunnable, Signal

from ..api.cliente import ErrorApi

log = logging.getLogger(__name__)


class _Senales(QObject):
    ok = Signal(object)
    error = Signal(str)


class Tarea(QRunnable):
    """Conectar `senales.ok`/`senales.error` a métodos de un QObject (no lambdas),
    así el resultado se procesa en el hilo de la pantalla."""

    def __init__(self, funcion, *args):
        super().__init__()
        self.funcion = funcion
        self.args = args
        self.senales = _Senales()

    def run(self) -> None:
        nombre = getattr(self.funcion, "__name__", self.funcion)
        try:
            resultado = self.funcion(*self.args)
        except ErrorApi as e:  # errores esperables (credenciales, validaciones): sin traza
            log.warning("%s: %s", nombre, e)
            self.senales.error.emit(str(e))
        except Exception as e:  # noqa: BLE001
            log.exception("Falló la tarea %s", nombre)
            self.senales.error.emit(str(e))
        else:
            self.senales.ok.emit(resultado)
