from __future__ import annotations

from collections import deque


class DetectorEstabilidad:
    """El peso es estable cuando las últimas N lecturas varían menos que la tolerancia."""

    def __init__(self, lecturas: int, tolerancia_kg: float):
        self._ventana: deque[float] = deque(maxlen=max(lecturas, 1))
        self._tolerancia = tolerancia_kg

    def agregar(self, kg: float) -> bool:
        self._ventana.append(kg)
        return len(self._ventana) == self._ventana.maxlen and max(self._ventana) - min(self._ventana) <= self._tolerancia

    def reiniciar(self) -> None:
        self._ventana.clear()
