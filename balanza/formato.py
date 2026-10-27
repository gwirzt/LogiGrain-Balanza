"""Formatos de presentación."""
from __future__ import annotations


def fmt_kg(valor: float | None) -> str:
    if valor is None:
        return "—"
    return f"{valor:,.0f}".replace(",", ".") + " kg"
