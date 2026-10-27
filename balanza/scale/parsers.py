"""Interpretación de las líneas que envía el indicador de la balanza.

Cada marca/modelo de cabezal tiene su formato. Cuando sepamos el modelo se agrega
una clase acá y se registra en PARSERS; el resto de la aplicación no cambia.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class ResultadoParseo:
    kg: float
    estable: bool | None = None  # None = el indicador no informa estabilidad


class Parser(Protocol):
    def parsear(self, linea: str) -> ResultadoParseo | None: ...


_NUMERO = re.compile(r"([-+]?)\s*(\d+(?:[.,]\d+)?)")


class ParserGenerico:
    """Toma el primer número de la línea (ej. ' 045320 kg' o 'ST,GS,+045320kg').
    Si la línea empieza con ST/US (estable/inestable), usa ese dato."""

    def parsear(self, linea: str) -> ResultadoParseo | None:
        m = _NUMERO.search(linea)
        if not m:
            return None
        kg = float(m.group(2).replace(",", "."))
        if m.group(1) == "-":
            kg = -kg
        cabecera = linea.lstrip().upper()
        estable = True if cabecera.startswith("ST") else False if cabecera.startswith("US") else None
        return ResultadoParseo(kg, estable)


PARSERS: dict[str, type] = {
    "generico": ParserGenerico,
}


def crear_parser(nombre: str) -> Parser:
    try:
        return PARSERS[nombre]()
    except KeyError:
        raise ValueError(f"Protocolo de balanza desconocido: {nombre!r}. Disponibles: {', '.join(PARSERS)}") from None
