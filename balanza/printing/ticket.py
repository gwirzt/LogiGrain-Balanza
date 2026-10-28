"""Ticket de pesaje, con el formato del ticket de balanza que ya se usa en el puerto (letra de máquina,
una línea por dato). Se imprime con el driver de Windows, así sirve tanto para impresoras térmicas de
80 mm como para A4, cambiando el tamaño en config.toml. Cada ticket se guarda además como PDF."""
from __future__ import annotations

import hashlib
from html import escape
from pathlib import Path

from ..config import TicketConfig
from ..models import EstadoPesaje, Operacion, Pesaje

SEPARADOR = "-" * 30


def _kg(valor: float | None) -> str:
    return "" if valor is None else f"{round(valor)} Kg."


def _hora(momento) -> str:
    return f"{momento:%d/%m/%Y %H:%M:%S}" if momento else ""


def _digito_luhn(numero: str) -> str:
    """Dígito verificador (algoritmo de Luhn): detecta un dígito mal copiado o dos dígitos invertidos."""
    total = 0
    for i, c in enumerate(reversed(numero)):
        d = int(c) * (2 if i % 2 == 0 else 1)
        total += d - 9 if d > 9 else d
    return str((10 - total % 10) % 10)


def codigo_validacion(p: Pesaje) -> str:
    """13 dígitos: 12 de un resumen de los datos del pesaje (puesto, número, CTG, pesos y horas) más un
    dígito verificador. Se recalcula con los datos de la base: si se altera un peso o una hora en el
    ticket, el código deja de coincidir. No depende del romaneo, así no cambia al reimprimir."""
    datos = "|".join([
        p.puesto, str(p.id), p.camion_id, str(round(p.peso1_kg)), str(round(p.peso2_kg or 0)),
        _hora(p.peso1_momento), _hora(p.peso2_momento),
    ])
    base = f"{int(hashlib.sha256(datos.encode()).hexdigest(), 16) % 10**12:012d}"
    return base + _digito_luhn(base)


def lineas_ticket(p: Pesaje, cfg: TicketConfig) -> list[str]:
    cerrado = p.estado is EstadoPesaje.CERRADO
    descarga = p.operacion is Operacion.DESCARGA
    chofer = "" if p.chofer == f"CUIT {p.chofer_cuit}" else p.chofer  # LogiGrain informa "CUIT …" sin nombre
    modo = "Modo Simulador" if p.simulado else "Modo Automatico"

    lineas = [cfg.empresa.upper(), SEPARADOR]
    if not cerrado:
        lineas += ["COMPROBANTE DE 1° PESAJE", ""]
    lineas += [
        f"Chofer : {chofer}",
        f"Cuit   : {p.chofer_cuit}",
        f"Ingreso : {_hora(p.fecha_ingreso)}",
    ]
    if cerrado:
        lineas.append(f"Salio   : {_hora(p.peso2_momento)}")
    lineas += [
        SEPARADOR,
        f"Fecha : {_hora(p.peso2_momento if cerrado else p.peso1_momento)}",
        f"Operador : {p.operador}",
        f"C. P.: {p.camion_id}   Código : {'' if p.cpe_id is None else p.cpe_id}",
        f"Patente : {p.patente}",
        f"Producto : {p.producto}",
    ]
    if not cerrado:
        tipo = "Bruto" if descarga else "Tara"  # 1° peso: descarga entra lleno, carga entra vacía
        return lineas + [
            f"{tipo}: {_kg(p.peso1_kg)}",
            f"Balanza       : {p.balanza1_nro or ''} {modo}",
        ]

    lineas += [
        f"Bruto: {_kg(p.bruto_kg)}",
        f"Tara : {_kg(p.tara_kg)}",
        f"{'Desc.' if descarga else 'Carg.'}: {_kg(p.neto_kg)}",
        "",
    ]
    if p.romaneo:
        r = p.romaneo
        mermas = r.get("mermas") or {}
        total = r.get("merma_total_kg", mermas.get("total_kg", 0)) or 0
        neto = r.get("peso_neto_kg") or p.neto_kg
        lineas += [
            f"Mermas   : {_kg(total)}",
            f"F. EST-  : {_kg(mermas.get('rubros_kg') or 0)}",  # merma fuera de estándar de calidad (rubros)
            f"Neto : {_kg(r.get('peso_neto_final_kg'))}",
        ]
    else:
        lineas.append("Mermas   : pendiente (sin romaneo de LogiGrain)")
    lineas += [
        f"Balanza       : {p.balanza2_nro or ''} {modo}",
        f"Liq:Grado {p.grado}",
    ]
    if p.romaneo:
        # El % se calcula sobre lo descargado: el total_pct que informa LogiGrain no siempre coincide con los kilos.
        lineas.append(f"Merma Total :{total * 100 / neto:.2f}" if neto else "Merma Total :")
    return lineas + ["", "", f"Validación: {codigo_validacion(p)}"]


def html_ticket(p: Pesaje, cfg: TicketConfig) -> str:
    texto = escape("\n".join(lineas_ticket(p, cfg)))
    return f"<pre style=\"font-family:'Courier New'; font-size:9pt\">{texto}</pre>"


def ruta_pdf(p: Pesaje, carpeta: str | Path) -> Path:
    """datos/tickets/AAAA-MM/BALANZA-1-000001_CTG10235570674.pdf (el comprobante de 1° peso lleva _1er_peso)."""
    cerrado = p.estado is EstadoPesaje.CERRADO
    momento = p.peso2_momento if cerrado else p.peso1_momento
    sufijo = "" if cerrado else "_1er_peso"
    return Path(carpeta) / f"{momento:%Y-%m}" / f"{p.numero}_CTG{p.camion_id}{sufijo}.pdf"


def _impresora(cfg: TicketConfig, nombre: str):
    from PySide6.QtCore import QMarginsF, QSizeF
    from PySide6.QtGui import QPageLayout, QPageSize
    from PySide6.QtPrintSupport import QPrinter

    impresora = QPrinter(QPrinter.PrinterMode.HighResolution)
    impresora.setPageSize(QPageSize(QSizeF(cfg.ancho_mm, cfg.alto_mm), QPageSize.Unit.Millimeter, "Ticket"))
    impresora.setPageMargins(QMarginsF(3, 3, 3, 3), QPageLayout.Unit.Millimeter)
    impresora.setDocName(nombre)
    return impresora


def _documento(p: Pesaje, cfg: TicketConfig):
    from PySide6.QtGui import QTextDocument

    documento = QTextDocument()
    documento.setHtml(html_ticket(p, cfg))
    return documento


def guardar_pdf(p: Pesaje, cfg: TicketConfig, carpeta: str | Path) -> Path:
    """Guarda el ticket como PDF. Si ya existía (reimpresión) se reemplaza por la versión actual."""
    from PySide6.QtPrintSupport import QPrinter

    ruta = ruta_pdf(p, carpeta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    impresora = _impresora(cfg, f"Ticket {p.numero}")
    impresora.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
    impresora.setOutputFileName(str(ruta))
    _documento(p, cfg).print_(impresora)
    return ruta


def imprimir_ticket(p: Pesaje, cfg: TicketConfig, parent=None) -> bool:
    from PySide6.QtPrintSupport import QPrintPreviewDialog

    impresora = _impresora(cfg, f"Ticket {p.numero}")
    if cfg.impresora:
        impresora.setPrinterName(cfg.impresora)
    documento = _documento(p, cfg)

    if cfg.vista_previa:
        dialogo = QPrintPreviewDialog(impresora, parent)
        dialogo.setWindowTitle(f"Ticket {p.numero}")
        dialogo.paintRequested.connect(documento.print_)
        return bool(dialogo.exec())
    documento.print_(impresora)
    return True
