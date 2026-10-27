"""Panel de un cabezal: título, visor de peso y botón para pesar en esa balanza."""
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from ..config import BalanzaConfig
from ..models import LecturaPeso
from ..scale.ciclo import CicloBalanza
from ..scale.hilo import HiloBalanza
from .visor import VisorPeso


class PanelBalanza(QWidget):
    pesar = Signal(int)  # nro de balanza
    cambio = Signal()  # cambió la lectura o la conexión: la ventana revisa qué botones habilitar

    def __init__(self, cfg: BalanzaConfig, atajo: str, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        self.nro = cfg.nro
        self.lectura: LecturaPeso | None = None
        self.conectada = False
        self.ciclo = CicloBalanza(cfg.umbral_cero_kg)

        self.lbl_titulo = QLabel(f"BALANZA {self.nro}")
        self.lbl_titulo.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        origen = "simulador" if cfg.modo == "simulador" else f"{cfg.puerto} · {cfg.baudios} baudios"
        self.lbl_conexion = QLabel(f"{origen} · conectando…")
        self.lbl_conexion.setStyleSheet("color: #9e9e9e;")
        self._origen = origen
        self.visor = VisorPeso()
        self.boton = QPushButton(f"Pesar en balanza {self.nro}   [{atajo}]")
        self.boton.setMinimumHeight(56)
        self.boton.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        self.boton.setEnabled(False)
        self.boton.clicked.connect(self._al_presionar)

        encabezado = QHBoxLayout()
        encabezado.addWidget(self.lbl_titulo)
        encabezado.addStretch(1)
        encabezado.addWidget(self.lbl_conexion)
        capa = QVBoxLayout(self)
        capa.setContentsMargins(0, 0, 0, 0)
        capa.addLayout(encabezado)
        capa.addWidget(self.visor)
        capa.addWidget(self.boton)

        self.hilo = HiloBalanza(cfg, self)
        self.hilo.lectura.connect(self._al_leer)
        self.hilo.conexion.connect(self._al_cambiar_conexion)

    def iniciar(self) -> None:
        self.hilo.start()

    def detener(self) -> None:
        self.hilo.requestInterruption()
        self.hilo.wait(3000)

    @property
    def lista(self) -> bool:
        return self.conectada and self.lectura is not None and self.lectura.estable

    def habilitar(self, habilitado: bool) -> None:
        if self.boton.isEnabled() != habilitado:
            self.boton.setEnabled(habilitado)

    def _al_presionar(self) -> None:
        self.pesar.emit(self.nro)

    def pesado(self) -> None:
        """Se registró un peso en esta balanza: queda en 0 hasta que baje el camión."""
        self.ciclo.pesado()
        if self.lectura is not None:
            self._al_leer(self.lectura)

    def _al_leer(self, lectura: LecturaPeso) -> None:
        self.lectura = self.ciclo.filtrar(lectura)
        if self.ciclo.en_cero:
            self.visor.en_cero(lectura)
        else:
            self.visor.mostrar(lectura)
        self.cambio.emit()

    def _al_cambiar_conexion(self, conectada: bool, mensaje: str) -> None:
        self.conectada = conectada
        self.lbl_conexion.setText(f"{self._origen} · {'conectada' if conectada else 'SIN CONEXIÓN'}")
        self.lbl_conexion.setStyleSheet("color: #9e9e9e;" if conectada else "color: #ef5350; font-weight: bold;")
        self.lbl_conexion.setToolTip(mensaje)
        if not conectada:
            self.lectura = None
            self.visor.sin_conexion(mensaje)
        self.cambio.emit()
