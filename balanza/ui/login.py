"""Pantalla de ingreso: valida usuario y contraseña contra la API de LogiGrain."""
from __future__ import annotations

from PySide6.QtCore import Qt, QThreadPool
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QVBoxLayout,
)

from ..api.cliente import ClienteLogigrain
from .tareas import Tarea


class DialogoLogin(QDialog):
    def __init__(self, cliente: ClienteLogigrain, servidor: str, usuario: str = "", contrasena: str = "",
                 parent=None):
        super().__init__(parent)
        self.cliente = cliente
        self._pool = QThreadPool(self)
        self.setWindowTitle("Ingreso — Balanza Logigrain")
        self.setMinimumWidth(420)

        titulo = QLabel("Balanza Logigrain")
        titulo.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        subtitulo = QLabel(f"Ingrese con su usuario de LogiGrain\n{servidor}")
        subtitulo.setStyleSheet("color: #888;")

        self.txt_usuario = QLineEdit(usuario)
        self.txt_contrasena = QLineEdit(contrasena)
        self.txt_contrasena.setEchoMode(QLineEdit.EchoMode.Password)
        formulario = QFormLayout()
        formulario.addRow("Usuario:", self.txt_usuario)
        formulario.addRow("Contraseña:", self.txt_contrasena)

        self.lbl_error = QLabel()
        self.lbl_error.setWordWrap(True)
        self.lbl_error.setStyleSheet("color: #ef5350;")
        self.lbl_error.hide()

        self.botones = QDialogButtonBox()
        self.btn_ingresar = self.botones.addButton("Ingresar", QDialogButtonBox.ButtonRole.AcceptRole)
        self.botones.addButton("Salir", QDialogButtonBox.ButtonRole.RejectRole)
        self.botones.accepted.connect(self._ingresar)
        self.botones.rejected.connect(self.reject)

        capa = QVBoxLayout(self)
        capa.addWidget(titulo)
        capa.addWidget(subtitulo)
        capa.addSpacing(8)
        capa.addLayout(formulario)
        capa.addWidget(self.lbl_error)
        capa.addWidget(self.botones)

        (self.txt_contrasena if usuario else self.txt_usuario).setFocus()

    def _ingresar(self) -> None:
        usuario = self.txt_usuario.text().strip()
        contrasena = self.txt_contrasena.text()
        if not usuario or not contrasena:
            self._mostrar_error("Complete usuario y contraseña.")
            return
        self._ocupado(True)
        tarea = Tarea(self.cliente.login, usuario, contrasena)
        tarea.senales.ok.connect(self._al_ingresar)
        tarea.senales.error.connect(self._al_fallar)
        self._pool.start(tarea)

    def _al_ingresar(self, _resultado) -> None:
        self._ocupado(False)
        self.accept()

    def _al_fallar(self, mensaje: str) -> None:
        self._ocupado(False)
        self._mostrar_error(mensaje)
        self.txt_contrasena.selectAll()
        self.txt_contrasena.setFocus()

    def _mostrar_error(self, mensaje: str) -> None:
        self.lbl_error.setText(mensaje)
        self.lbl_error.show()

    def _ocupado(self, ocupado: bool) -> None:
        self.btn_ingresar.setEnabled(not ocupado)
        self.btn_ingresar.setText("Ingresando…" if ocupado else "Ingresar")
        self.txt_usuario.setEnabled(not ocupado)
        self.txt_contrasena.setEnabled(not ocupado)
        if ocupado:
            self.setCursor(Qt.CursorShape.WaitCursor)
        else:
            self.unsetCursor()

    def reject(self) -> None:
        if self.btn_ingresar.isEnabled():  # no cerrar mientras hay un login en curso
            super().reject()
