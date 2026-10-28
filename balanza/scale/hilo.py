"""Hilo que lee la balanza en forma continua sin trabar la pantalla."""
from __future__ import annotations

import logging
import time

from PySide6.QtCore import QThread, Signal

from ..config import BalanzaConfig
from ..models import LecturaPeso
from .estabilidad import DetectorEstabilidad
from .fuentes import FuenteSerie, FuenteSimulada
from .parsers import crear_parser

log = logging.getLogger(__name__)

SEGUNDOS_SIN_DATOS = 3.0
SEGUNDOS_REINTENTO = 3.0


class HiloBalanza(QThread):
    lectura = Signal(object)  # LecturaPeso
    conexion = Signal(bool, str)  # conectada, mensaje

    def __init__(self, cfg: BalanzaConfig, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        self.simulado = cfg.modo == "simulador"  # se puede cambiar en caliente con cambiar_modo
        self.simulador = FuenteSimulada(division_kg=cfg.division_kg)  # persiste entre reconexiones
        self._reconectar = False

    def cambiar_modo(self, simulado: bool) -> None:
        """Pasa de puerto serie a simulador o al revés; el hilo cierra la fuente actual y abre la otra."""
        if simulado != self.simulado:
            self.simulado = simulado
            self._reconectar = True

    def simular(self, tipo: str) -> None:
        """Sube un camión simulado ("TARA" o "BRUTO"). Con el puerto serie no hace nada."""
        if self.simulado:
            self.simulador.subir(tipo)

    def bajar_camion(self) -> None:
        self.simulador.bajar()

    def run(self) -> None:
        parser = crear_parser(self.cfg.protocolo)
        detector = DetectorEstabilidad(self.cfg.lecturas_estables, self.cfg.tolerancia_kg)
        while not self.isInterruptionRequested():
            self._reconectar = False
            fuente = self.simulador if self.simulado else FuenteSerie(self.cfg)
            try:
                fuente.abrir()
                log.info("Balanza conectada: %s", fuente.descripcion)
                self._leer(fuente, parser, detector)
            except Exception as e:  # noqa: BLE001 - puerto ocupado, cable desconectado, etc.
                log.warning("Error de balanza (%s): %s", fuente.descripcion, e)
                self.conexion.emit(False, f"{fuente.descripcion}: {e}")
                self._esperar(SEGUNDOS_REINTENTO)
            finally:
                fuente.cerrar()
                detector.reiniciar()

    def _leer(self, fuente, parser, detector) -> None:
        con_datos = False
        ultimo_dato = time.monotonic()
        while not self.isInterruptionRequested() and not self._reconectar:
            linea = fuente.leer_linea()
            resultado = parser.parsear(linea) if linea else None
            if resultado is None:
                if linea:
                    log.debug("Línea no reconocida del indicador: %r", linea)
                if con_datos and time.monotonic() - ultimo_dato > SEGUNDOS_SIN_DATOS:
                    con_datos = False
                    detector.reiniciar()
                    self.conexion.emit(False, "Sin datos del indicador")
                continue
            if not con_datos:
                con_datos = True
                self.conexion.emit(True, fuente.descripcion)
            ultimo_dato = time.monotonic()
            estable = detector.agregar(resultado.kg) and resultado.estable is not False
            self.lectura.emit(LecturaPeso(resultado.kg, estable, linea))

    def _esperar(self, segundos: float) -> None:
        fin = time.monotonic() + segundos
        while time.monotonic() < fin and not self.isInterruptionRequested() and not self._reconectar:
            self.msleep(100)
