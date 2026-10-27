"""Visor grande del peso en tiempo real."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel

from ..formato import fmt_kg
from ..models import LecturaPeso

VERDE = "#4caf50"
AMBAR = "#ffb300"
ROJO = "#ef5350"
GRIS = "#9e9e9e"


class VisorPeso(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("visor")
        self.lbl_peso = QLabel("------")
        self.lbl_peso.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.lbl_peso.setFont(QFont("Consolas", 60, QFont.Weight.Bold))
        self.lbl_estado = QLabel("CONECTANDO…")
        self.lbl_estado.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        self.lbl_estado.setMinimumWidth(240)
        self.lbl_estado.setAlignment(Qt.AlignmentFlag.AlignCenter)

        capa = QHBoxLayout(self)
        capa.setContentsMargins(24, 8, 24, 8)
        capa.addWidget(self.lbl_estado)
        capa.addWidget(self.lbl_peso, 1)

        self._color = ""
        self._pintar(GRIS)

    def mostrar(self, lectura: LecturaPeso) -> None:
        self.lbl_peso.setText(fmt_kg(lectura.kg))
        self.lbl_estado.setText("ESTABLE" if lectura.estable else "EN MOVIMIENTO")
        self.setToolTip(lectura.crudo)
        self._pintar(VERDE if lectura.estable else AMBAR)

    def en_cero(self, lectura: LecturaPeso) -> None:
        """Peso ya registrado: muestra 0 hasta que el camión baje de la balanza."""
        self.lbl_peso.setText(fmt_kg(0))
        self.lbl_estado.setText("PESADO · BAJE\nEL CAMIÓN")
        self.setToolTip(f"Peso actual en el indicador: {fmt_kg(lectura.kg)}")
        self._pintar(GRIS)

    def sin_conexion(self, mensaje: str) -> None:
        self.lbl_peso.setText("------")
        self.lbl_estado.setText("SIN CONEXIÓN")
        self.setToolTip(mensaje)
        self._pintar(ROJO)

    def _pintar(self, color: str) -> None:
        if color == self._color:
            return
        self._color = color
        self.setStyleSheet(f"#visor {{ background: #111; border-radius: 8px; }} QLabel {{ color: {color}; }}")
