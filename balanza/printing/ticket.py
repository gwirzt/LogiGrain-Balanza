"""Ticket de pesaje. Se imprime con el driver de Windows, así sirve tanto para
impresoras térmicas de 80 mm como para A4, cambiando el tamaño en config.toml."""
from __future__ import annotations

from html import escape

from ..config import TicketConfig
from ..formato import fmt_kg
from ..models import EstadoPesaje, Pesaje


def html_ticket(p: Pesaje, cfg: TicketConfig) -> str:
    def fila(etiqueta: str, valor: str) -> str:
        return f"<tr><td>{escape(etiqueta)}</td><td align='right'>{escape(valor)}</td></tr>"

    def hora(m) -> str:
        return m.strftime("%d/%m/%Y %H:%M") if m else "—"

    def balanza(nro) -> str:
        return f" (B{nro})" if nro else ""

    cerrado = p.estado is EstadoPesaje.CERRADO
    titulo = "TICKET DE PESAJE" if cerrado else "COMPROBANTE DE 1° PESAJE"
    datos = [
        ("CTG", p.camion_id),
        ("Patente", p.patente),
        ("Acoplado", p.patente_acoplado or "—"),
        ("Chofer", p.chofer or "—"),
        ("Transportista", p.transportista or "—"),
        ("Producto", p.producto or "—"),
        ("Destinatario", p.destinatario or "—"),
        ("Operación", str(p.operacion).capitalize()),
    ]
    if cerrado:
        pesos = [
            (f"1° peso{balanza(p.balanza1_nro)}  " + hora(p.peso1_momento), fmt_kg(p.peso1_kg)),
            (f"2° peso{balanza(p.balanza2_nro)}  " + hora(p.peso2_momento), fmt_kg(p.peso2_kg)),
            ("Bruto", fmt_kg(p.bruto_kg)),
            ("Tara", fmt_kg(p.tara_kg)),
        ]
        neto = f"<p align='center' style='font-size:16pt'><b>NETO: {escape(fmt_kg(p.neto_kg))}</b></p>"
    else:
        pesos = [(f"1° peso{balanza(p.balanza1_nro)}  " + hora(p.peso1_momento), fmt_kg(p.peso1_kg))]
        neto = ""

    return f"""
    <div style="font-family:'Arial'; font-size:9pt">
      <p align="center" style="font-size:12pt"><b>{escape(cfg.empresa)}</b></p>
      <p align="center"><b>{titulo}</b><br>N° {escape(p.numero)}</p>
      <hr>
      <table width="100%">{''.join(fila(e, v) for e, v in datos)}</table>
      <hr>
      <table width="100%">{''.join(fila(e, v) for e, v in pesos)}</table>
      {neto}
      <hr>
      <br><br>
      <p align="center">______________________<br>Firma chofer</p>
    </div>
    """


def imprimir_ticket(p: Pesaje, cfg: TicketConfig, parent=None) -> bool:
    from PySide6.QtCore import QMarginsF, QSizeF
    from PySide6.QtGui import QPageLayout, QPageSize, QTextDocument
    from PySide6.QtPrintSupport import QPrinter, QPrintPreviewDialog

    impresora = QPrinter(QPrinter.PrinterMode.HighResolution)
    if cfg.impresora:
        impresora.setPrinterName(cfg.impresora)
    impresora.setPageSize(QPageSize(QSizeF(cfg.ancho_mm, cfg.alto_mm), QPageSize.Unit.Millimeter, "Ticket"))
    impresora.setPageMargins(QMarginsF(3, 3, 3, 3), QPageLayout.Unit.Millimeter)
    impresora.setDocName(f"Ticket {p.numero}")

    documento = QTextDocument()
    documento.setHtml(html_ticket(p, cfg))

    if cfg.vista_previa:
        dialogo = QPrintPreviewDialog(impresora, parent)
        dialogo.setWindowTitle(f"Ticket {p.numero}")
        dialogo.paintRequested.connect(documento.print_)
        return bool(dialogo.exec())
    documento.print_(impresora)
    return True
