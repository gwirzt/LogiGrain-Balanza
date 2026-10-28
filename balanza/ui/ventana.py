"""Ventana principal del puesto de balanza."""
from __future__ import annotations

import logging
from datetime import date, datetime, time

from PySide6.QtCore import Qt, QThreadPool, QTimer
from PySide6.QtGui import QFont, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..api.cliente import ClienteLogigrain, ErrorApi
from ..config import AppConfig
from ..ficha import armar_ficha, proximo_paso
from ..formato import fmt_kg
from ..models import Camion, EstadoPesaje, Pesaje
from ..printing.ticket import guardar_pdf, imprimir_ticket
from ..services.pesaje import EVENTO_SEGUNDO_PESO, ErrorPesaje, ServicioPesaje
from ..services.sync import ResultadoSync, Sincronizador
from ..storage.db import BaseDatos
from .panel_balanza import PanelBalanza
from .tareas import Tarea

log = logging.getLogger(__name__)

ATAJOS_PESAR = ["F2", "F3"]  # balanza izquierda, balanza derecha
COLOR_PROXIMO = "#4caf50"
COLOR_ERROR = "#ef5350"
COLOR_AVISO = "#ffb300"


def _tabla(columnas: list[str]) -> QTableWidget:
    t = QTableWidget(0, len(columnas))
    t.setHorizontalHeaderLabels(columnas)
    t.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    t.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    t.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    t.setAlternatingRowColors(True)
    t.verticalHeader().setVisible(False)
    t.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
    return t


def _llenar(tabla: QTableWidget, filas: list[list[str]]) -> None:
    tabla.setRowCount(len(filas))
    for i, fila in enumerate(filas):
        for j, valor in enumerate(fila):
            tabla.setItem(i, j, QTableWidgetItem(valor))


def _vaciar(capa) -> None:
    while capa.count():
        widget = capa.takeAt(0).widget()
        if widget is not None:
            widget.deleteLater()


class VentanaPrincipal(QMainWindow):
    def __init__(
        self,
        cfg: AppConfig,
        db: BaseDatos,
        cliente: ClienteLogigrain,
        servicio: ServicioPesaje,
        sincronizador: Sincronizador,
    ):
        super().__init__()
        self.cfg = cfg
        self.db = db
        self.cliente = cliente
        self.servicio = servicio
        self.sincronizador = sincronizador

        self._pool = QThreadPool(self)
        self._camion: Camion | None = None  # CTG consultado y validado, listo para pesar
        self._ctg_consultando = ""
        self._pesaje: Pesaje | None = None  # último pesaje registrado (para imprimir)
        self._pesajes_hoy: list[Pesaje] = []
        self._sync_en_curso = False
        self._resincronizar = False  # se pidió sincronizar mientras había otra en curso
        self._tickets_pendientes: list[int] = []  # pesajes cerrados que esperan la respuesta de LogiGrain

        self.setWindowTitle(f"Balanza Logigrain — {cfg.puesto}")
        self._armar_ui()
        self._armar_atajos()
        for panel in self.paneles.values():
            panel.iniciar()

        self._timer_sync = QTimer(self)
        self._timer_sync.setInterval(cfg.api.intervalo_sync_s * 1000)
        self._timer_sync.timeout.connect(self.sincronizar)
        self._timer_sync.start()

        self.refrescar_pesajes()
        self.sincronizar()
        self.txt_ctg.setFocus()

    # --- Armado de la pantalla -------------------------------------------------

    def _armar_ui(self) -> None:
        # Cabezales: balanza 1 arriba a la izquierda, balanza 2 arriba a la derecha.
        self.paneles: dict[int, PanelBalanza] = {}
        # Mismo criterio que bloquea el arranque: no registrar pesos simulados en LogiGrain salvo en pruebas.
        permitir_simulador = self.cfg.api.simulador_permitido
        fila_balanzas = QHBoxLayout()
        fila_balanzas.setSpacing(24)
        for balanza, atajo in zip(self.cfg.balanzas, ATAJOS_PESAR):
            panel = PanelBalanza(balanza, atajo, permitir_simulador)
            panel.pesar.connect(self.pesar)
            panel.cambio.connect(self._actualizar_botones)
            panel.btn_simulador.toggled.connect(lambda _, p=panel: self._al_cambiar_simulador(p))
            self.paneles[balanza.nro] = panel
            fila_balanzas.addWidget(panel, 1)
        if len(self.paneles) == 1:
            fila_balanzas.addStretch(1)  # una sola balanza: queda a la izquierda

        # Consulta del CTG
        self.txt_ctg = QLineEdit(placeholderText="Número de CTG")
        self.txt_ctg.setFont(QFont("Consolas", 20, QFont.Weight.Bold))
        self.txt_ctg.setMaxLength(20)
        self.txt_ctg.setMinimumWidth(320)
        self.txt_ctg.returnPressed.connect(self.consultar)
        self.btn_consultar = QPushButton("Consultar  [Enter]")
        self.btn_consultar.setMinimumHeight(44)
        self.btn_consultar.clicked.connect(self.consultar)
        self.btn_limpiar = QPushButton("Limpiar  [Esc]")
        self.btn_limpiar.setMinimumHeight(44)
        self.btn_limpiar.clicked.connect(self.limpiar)
        self.lbl_proximo = QLabel()
        self.lbl_proximo.setFont(QFont("Segoe UI", 18, QFont.Weight.Bold))
        self.lbl_proximo.setWordWrap(True)

        barra = QHBoxLayout()
        barra.addWidget(QLabel("CTG:"))
        barra.addWidget(self.txt_ctg)
        barra.addWidget(self.btn_consultar)
        barra.addWidget(self.btn_limpiar)
        barra.addSpacing(24)
        barra.addWidget(self.lbl_proximo, 1)

        self.lbl_advertencias = QLabel()
        self.lbl_advertencias.setWordWrap(True)
        self.lbl_advertencias.setStyleSheet(f"color: {COLOR_ERROR}; font-weight: bold; font-size: 11pt;")
        self.lbl_advertencias.hide()

        self.grilla_ficha = QGridLayout()
        self.grilla_ficha.setSpacing(12)
        contenedor_ficha = QWidget()
        contenedor_ficha.setLayout(self.grilla_ficha)

        grp_ctg = QGroupBox("Carta de Porte")
        capa = QVBoxLayout(grp_ctg)
        capa.addLayout(barra)
        capa.addWidget(self.lbl_advertencias)
        capa.addWidget(contenedor_ficha, 1)

        # Pesajes del día
        self.tabla_pesajes = _tabla(
            ["N°", "Hora", "CTG", "Patente", "Producto", "1° peso", "2° peso", "Neto", "Estado"]
        )
        self.tabla_pesajes.itemDoubleClicked.connect(self._reimprimir_desde_tabla)
        self.btn_imprimir = QPushButton("Imprimir último ticket  [F5]")
        self.btn_imprimir.clicked.connect(self.imprimir)
        grp_hoy = QGroupBox("Pesajes de hoy  (doble clic para reimprimir)")
        capa = QVBoxLayout(grp_hoy)
        capa.addWidget(self.tabla_pesajes)
        capa.addWidget(self.btn_imprimir, 0, Qt.AlignmentFlag.AlignRight)

        central = QWidget()
        capa = QVBoxLayout(central)
        capa.addLayout(fila_balanzas)
        capa.addWidget(grp_ctg, 3)
        capa.addWidget(grp_hoy, 2)
        self.setCentralWidget(central)

        self.lbl_sync = QLabel("Envíos pendientes: —")
        self.statusBar().addPermanentWidget(self.lbl_sync)
        self.statusBar().addPermanentWidget(
            QLabel(f"Usuario: {self.cliente.usuario} · Puerto: {self.cliente.puerto} · Puesto: {self.cfg.puesto}")
        )
        if self.cfg.api.modo == "http" and not self.cfg.api.enviar_pesos:
            aviso = QLabel("MODO PRUEBA: los pesos no se envían a LogiGrain")
            aviso.setStyleSheet(f"color: {COLOR_AVISO}; font-weight: bold;")
            self.statusBar().addPermanentWidget(aviso)
        if self.cfg.api.envia_pesos_simulados:
            self.lbl_simulador = QLabel("SIMULADOR ACTIVO: SE ENVÍAN PESOS FICTICIOS A LOGIGRAIN")
            self.lbl_simulador.setStyleSheet(f"color: {COLOR_ERROR}; font-weight: bold;")
        else:
            self.lbl_simulador = QLabel("SIMULADOR ACTIVO")
            self.lbl_simulador.setStyleSheet(f"color: {COLOR_AVISO}; font-weight: bold;")
        self.statusBar().addPermanentWidget(self.lbl_simulador)
        self.lbl_simulador.setVisible(any(p.simulado for p in self.paneles.values()))

        self._mostrar_mensaje("Ingrese el CTG y presione Enter.", "#9e9e9e")
        self._actualizar_botones()

    def _armar_atajos(self) -> None:
        for nro, atajo in zip(self.paneles, ATAJOS_PESAR):
            QShortcut(QKeySequence(atajo), self, activated=self.paneles[nro].boton.click)
            QShortcut(QKeySequence(f"Ctrl+{atajo}"), self, activated=self.paneles[nro].btn_simulador.click)
        QShortcut(QKeySequence("F5"), self, activated=self.imprimir)
        QShortcut(QKeySequence("Escape"), self, activated=self.limpiar)
        QShortcut(QKeySequence("Ctrl+F"), self, activated=self._enfocar_ctg)

    def _enfocar_ctg(self) -> None:
        self.txt_ctg.setFocus()
        self.txt_ctg.selectAll()

    # --- Consulta del CTG ------------------------------------------------------

    def consultar(self) -> None:
        ctg = self.txt_ctg.text().strip()
        if not ctg:
            return
        self._camion = None
        self._ctg_consultando = ctg
        self._mostrar_ficha(None)
        self._mostrar_mensaje(f"Consultando CTG {ctg}…", "#9e9e9e")
        self.btn_consultar.setEnabled(False)
        self._actualizar_botones()
        tarea = Tarea(self._consultar_ctg, ctg)
        tarea.senales.ok.connect(self._al_recibir_ctg)
        tarea.senales.error.connect(self._al_fallar_consulta)
        self._pool.start(tarea)

    def _consultar_ctg(self, ctg: str) -> tuple[str, Camion | None, str]:
        # Corre en segundo plano. Devuelve el CTG para descartar respuestas de una consulta anterior.
        try:
            return ctg, self.cliente.consultar_ctg(ctg), ""
        except ErrorApi as e:
            return ctg, None, str(e)

    def _al_recibir_ctg(self, resultado: tuple[str, Camion | None, str]) -> None:
        ctg, camion, error = resultado
        self.btn_consultar.setEnabled(True)
        if ctg != self._ctg_consultando:
            return
        if camion is None:
            self._mostrar_mensaje(f"No se puede pesar: {error}", COLOR_ERROR)
            self._bajar_camiones_simulados()
            self._enfocar_ctg()
        else:
            self._camion = camion
            ficha = armar_ficha(camion)
            self._mostrar_ficha(ficha)
            self._mostrar_mensaje(f"Próximo: {ficha.proximo}", COLOR_PROXIMO)
            self._subir_camiones_simulados()
        self._actualizar_botones()

    def _al_fallar_consulta(self, mensaje: str) -> None:
        self.btn_consultar.setEnabled(True)
        self._mostrar_mensaje(f"No se pudo consultar el CTG: {mensaje}", COLOR_ERROR)

    def limpiar(self) -> None:
        self._camion = None
        self._ctg_consultando = ""
        self.txt_ctg.clear()
        self._mostrar_ficha(None)
        self._bajar_camiones_simulados()
        self._mostrar_mensaje("Ingrese el CTG y presione Enter.", "#9e9e9e")
        self._actualizar_botones()
        self.txt_ctg.setFocus()

    # --- Simulador -------------------------------------------------------------

    def _subir_camiones_simulados(self, paneles: list[PanelBalanza] | None = None) -> None:
        """Con un CTG consultado, sube a cada balanza simulada un camión con el peso que corresponde
        (tara o bruto según la operación y si es el 1° o el 2° peso)."""
        if self._camion is None:
            return
        _, tipo = proximo_paso(self._camion)
        for panel in paneles or self.paneles.values():
            panel.simular_camion(tipo)

    def _bajar_camiones_simulados(self) -> None:
        for panel in self.paneles.values():
            panel.bajar_camion()

    def _al_cambiar_simulador(self, panel: PanelBalanza) -> None:
        self.lbl_simulador.setVisible(any(p.simulado for p in self.paneles.values()))
        self._subir_camiones_simulados([panel])

    def _mostrar_mensaje(self, texto: str, color: str) -> None:
        self.lbl_proximo.setText(texto)
        self.lbl_proximo.setStyleSheet(f"color: {color};")

    def _mostrar_ficha(self, ficha) -> None:
        _vaciar(self.grilla_ficha)
        if ficha is None:
            self.lbl_advertencias.hide()
            return
        self.lbl_advertencias.setText("\n".join(f"⚠ {a}" for a in ficha.advertencias))
        self.lbl_advertencias.setVisible(bool(ficha.advertencias))
        columnas = 3
        for i, (titulo, filas) in enumerate(ficha.secciones):
            grupo = QGroupBox(titulo)
            formulario = QFormLayout(grupo)
            for etiqueta, valor in filas:
                lbl = QLabel(valor)
                lbl.setWordWrap(True)
                lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
                if etiqueta in ("CTG", "Patente", "Grano"):
                    lbl.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
                formulario.addRow(f"{etiqueta}:", lbl)
            self.grilla_ficha.addWidget(grupo, i // columnas, i % columnas)

    def _actualizar_botones(self) -> None:
        for panel in self.paneles.values():
            panel.habilitar(self._camion is not None and panel.lista)
        self.btn_imprimir.setEnabled(self._pesaje is not None)

    # --- Pesaje e impresión ----------------------------------------------------

    def pesar(self, nro: int) -> None:
        panel = self.paneles.get(nro)
        if self._camion is None or panel is None or not panel.boton.isEnabled():
            return
        try:
            pesaje = self.servicio.capturar(self._camion, panel.lectura, nro, simulado=panel.simulado)
        except ErrorPesaje as e:
            QMessageBox.warning(self, "No se pudo pesar", str(e))
            return

        self._pesaje = pesaje
        cerrado = pesaje.estado is EstadoPesaje.CERRADO
        # La balanza queda en 0 hasta que baje el camión, y se limpia el CTG: un F2/F3 repetido no registra
        # otro peso. Mientras sube el próximo camión ya se puede ingresar su CTG.
        panel.pesado()
        self.limpiar()
        if cerrado:
            # El ticket se imprime cuando LogiGrain responde: la respuesta trae el romaneo (mermas y neto final).
            self._tickets_pendientes.append(pesaje.id)
            texto = (f"✔ CTG {pesaje.camion_id}: 2° peso {fmt_kg(pesaje.peso2_kg)} en balanza {nro}. "
                     f"Neto {fmt_kg(pesaje.neto_kg)}. Enviando a LogiGrain para el romaneo…")
        else:
            texto = f"✔ CTG {pesaje.camion_id}: 1° peso {fmt_kg(pesaje.peso1_kg)} en balanza {nro}."
        self._mostrar_mensaje(texto, COLOR_PROXIMO)
        self.refrescar_pesajes()
        self.sincronizar()

    def imprimir(self, pesaje: Pesaje | None = None) -> None:
        pesaje = pesaje or self._pesaje
        if pesaje is None:
            return
        pesaje = self.db.obtener_pesaje(pesaje.id) or pesaje  # con el romaneo, si llegó después
        self._guardar_pdf(pesaje)
        try:
            imprimir_ticket(pesaje, self.cfg.ticket, self)
        except Exception as e:  # noqa: BLE001
            log.exception("Error al imprimir el ticket %s", pesaje.numero)
            QMessageBox.critical(self, "Impresión", f"No se pudo imprimir el ticket.\n\n{e}")

    def _guardar_pdf(self, pesaje: Pesaje) -> None:
        # Antes de la vista previa: el PDF queda aunque se cancele la impresión.
        if not self.cfg.ticket.guardar_pdf:
            return
        try:
            ruta = guardar_pdf(pesaje, self.cfg.ticket, self.cfg.carpeta_tickets)
        except Exception as e:  # noqa: BLE001 - no impide imprimir
            log.exception("No se pudo guardar el PDF del ticket %s", pesaje.numero)
            self.statusBar().showMessage(f"No se pudo guardar el PDF del ticket: {e}", 15000)
        else:
            log.info("Ticket %s guardado en %s", pesaje.numero, ruta)

    def _imprimir_tickets_pendientes(self, error: str) -> None:
        pendientes, self._tickets_pendientes = self._tickets_pendientes, []
        for pesaje_id in pendientes:
            pesaje = self.db.obtener_pesaje(pesaje_id)
            if pesaje is None:
                continue
            if self.db.envio_pendiente(pesaje_id, EVENTO_SEGUNDO_PESO):
                respuesta = QMessageBox.question(
                    self, "LogiGrain no respondió",
                    f"No se pudo registrar el 2° peso del CTG {pesaje.camion_id} en LogiGrain"
                    f"{': ' + error if error else '.'}\n\n"
                    "El peso quedó guardado y se reenvía solo cuando vuelva la conexión.\n\n"
                    "¿Imprimir el ticket ahora, sin el romaneo (mermas y neto final)?\n"
                    "Si elige No, puede imprimirlo después con F5 o con doble clic en Pesajes de hoy.",
                )
                if respuesta != QMessageBox.StandardButton.Yes:
                    continue
            self.imprimir(pesaje)

    def _reimprimir_desde_tabla(self, item: QTableWidgetItem) -> None:
        self.imprimir(self._pesajes_hoy[item.row()])

    def refrescar_pesajes(self) -> None:
        self._pesajes_hoy = self.db.pesajes_desde(datetime.combine(date.today(), time.min))
        _llenar(self.tabla_pesajes, [
            [p.numero, p.peso1_momento.strftime("%H:%M"), p.camion_id, p.patente, p.producto, fmt_kg(p.peso1_kg),
             fmt_kg(p.peso2_kg), fmt_kg(p.neto_kg), str(p.estado).capitalize()]
            for p in self._pesajes_hoy
        ])
        self._actualizar_botones()

    # --- Sincronización con la API ---------------------------------------------

    def sincronizar(self) -> None:
        if self._sync_en_curso:
            self._resincronizar = True  # la que está en curso pudo leer la cola antes del último peso
            return
        self._sync_en_curso = True
        tarea = Tarea(self.sincronizador.ejecutar)
        tarea.senales.ok.connect(self._al_terminar_sync)
        tarea.senales.error.connect(self._al_fallar_sync)
        self._pool.start(tarea)

    def _al_terminar_sync(self, r: ResultadoSync) -> None:
        self._sync_en_curso = False
        self.lbl_sync.setText(f"Envíos pendientes: {r.pendientes}")
        self.lbl_sync.setStyleSheet("color: #c62828; font-weight: bold;" if r.pendientes else "")
        self.lbl_sync.setToolTip(r.ultimo_error or "Todo enviado a LogiGrain")
        if self._resincronizar:
            self._resincronizar = False
            self.sincronizar()
            return
        self._imprimir_tickets_pendientes(r.ultimo_error)

    def _al_fallar_sync(self, mensaje: str) -> None:
        self._sync_en_curso = False
        self._resincronizar = False
        self.lbl_sync.setText("Envíos: error")
        self.lbl_sync.setToolTip(mensaje)
        self._imprimir_tickets_pendientes(mensaje)

    # --- Cierre ----------------------------------------------------------------

    def closeEvent(self, evento) -> None:
        self._timer_sync.stop()
        for panel in self.paneles.values():
            panel.detener()
        self._pool.waitForDone(5000)
        super().closeEvent(evento)
