"""Datos de la Carta de Porte que el operador ve antes de pesar."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from .formato import fmt_kg
from .models import Camion, Operacion

ESTADOS_CALADA = {"A": "Autorizada", "D": "Demorada", "R": "Rechazada"}


@dataclass
class Ficha:
    proximo: str  # ej. "1° PESO — BRUTO (descarga)"
    secciones: list[tuple[str, list[tuple[str, str]]]]
    advertencias: list[str] = field(default_factory=list)


def _texto(valor) -> str:
    return "—" if valor in (None, "") else str(valor)


def _fecha(valor) -> datetime | None:
    try:
        return datetime.fromisoformat(str(valor)) if valor else None
    except ValueError:
        return None


def _fmt_fecha(valor) -> str:
    f = _fecha(valor)
    return f.strftime("%d/%m/%Y %H:%M") if f else "—"


def _cosecha(valor) -> str:
    # LogiGrain informa la cosecha como 2526 → 2025/26
    s = str(valor or "")
    return f"20{s[:2]}/{s[2:]}" if len(s) == 4 and s.isdigit() else _texto(valor)


def _persona(nombre, cuit) -> str:
    nombre = (nombre or "").strip()
    if cuit and str(cuit) not in nombre:
        return f"{nombre} (CUIT {cuit})" if nombre else f"CUIT {cuit}"
    return nombre or "—"


def proximo_paso(camion: Camion) -> tuple[int, str]:
    """Número de peso que corresponde (1 o 2) y si es bruto o tara, según la posición y la operación."""
    numero = 2 if camion.posicion == "CON_PRIMER_PESO" else 1
    descarga = camion.operacion is Operacion.DESCARGA
    tipo = ("BRUTO" if numero == 1 else "TARA") if descarga else ("TARA" if numero == 1 else "BRUTO")
    return numero, tipo


def armar_ficha(camion: Camion, ahora: datetime | None = None) -> Ficha:
    d = camion.datos
    ahora = ahora or datetime.now()
    numero, tipo = proximo_paso(camion)
    proximo = f"{numero}° PESO — {tipo}  ({str(camion.operacion).lower()})"

    advertencias = []
    vencimiento = _fecha(d.get("fecha_vencimiento"))
    texto_venc = _fmt_fecha(d.get("fecha_vencimiento"))
    if vencimiento and vencimiento < ahora:
        advertencias.append(f"La Carta de Porte venció el {vencimiento:%d/%m/%Y %H:%M}.")
        texto_venc += "  (VENCIDA)"
    calada = d.get("calada_estado")
    if calada and calada != "A":
        advertencias.append(f"Calada {ESTADOS_CALADA.get(calada, calada)}.")
    if d.get("puede_pesar") is False:
        advertencias.append("LogiGrain indica que esta Carta de Porte no se puede pesar.")

    cpe = "—"
    if d.get("sucursal") is not None and d.get("nro_orden") is not None:
        cpe = f"{int(d['sucursal']):05d}-{int(d['nro_orden']):08d}"
    intervinientes = d.get("intervinientes") or {}

    pesos = [
        ("Declarado en CPE",
         f"Bruto {fmt_kg(d.get('peso_bruto'))} · Tara {fmt_kg(d.get('peso_tara'))} · Neto {fmt_kg(d.get('peso_neto'))}"),
    ]
    if camion.primer_peso_kg is not None:
        balanza = f" · balanza {camion.primer_peso_balanza_nro}" if camion.primer_peso_balanza_nro else ""
        hora = f" · {camion.primer_peso_momento:%d/%m %H:%M}" if camion.primer_peso_momento else ""
        pesos.append(("1° peso en balanza", f"{fmt_kg(camion.primer_peso_kg)}{balanza}{hora}"))

    secciones = [
        ("Carta de Porte", [
            ("CTG", camion.id),
            ("CPE N°", cpe),
            ("Estado", f"{_texto(d.get('estado'))} · {_texto(camion.posicion_label)}"),
            ("Vencimiento", texto_venc),
            ("Turno", _texto(camion.turno)),
            ("Régimen", _texto(d.get("regimen_descripcion"))),
        ]),
        ("Vehículo", [
            ("Patente", _texto(camion.patente)),
            ("Acoplado", _texto(camion.patente_acoplado)),
            ("Transportista", _persona(camion.transportista, d.get("cuit_transportista"))),
            ("Chofer", _persona(camion.chofer, d.get("cuit_chofer"))),
        ]),
        ("Mercadería", [
            ("Grano", f"{_texto(camion.producto)} · cosecha {_cosecha(d.get('cosecha'))}"),
            ("Operación", str(camion.operacion).capitalize()),
            ("Origen", _texto(d.get("origen_nombre"))),
            ("Destinatario", _texto(camion.destinatario)),
            ("Entregador", _texto(intervinientes.get("representante_entregador_nombre"))),
            ("Observaciones", _texto(d.get("observaciones"))),
        ]),
        ("Calada", [
            ("Estado", ESTADOS_CALADA.get(calada, _texto(calada))),
            ("Humedad", f"{d['calada_humedad_pct']} %" if d.get("calada_humedad_pct") is not None else "—"),
            ("Grado", _texto(d.get("calada_grado"))),
            ("Merma total", f"{d['calada_pct_total']} %" if d.get("calada_pct_total") is not None else "—"),
            ("Fumigada", "Sí" if d.get("mercaderia_fumigada") else "No"),
        ]),
        ("Pesos", pesos),
    ]
    return Ficha(proximo, secciones, advertencias)
