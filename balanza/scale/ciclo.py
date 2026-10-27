"""Ciclo de cada balanza: después de pesar queda en 0 hasta que el camión baje."""
from __future__ import annotations

from ..models import LecturaPeso


class CicloBalanza:
    """Tras registrar un peso la balanza se "pone en 0": se ignora el peso del camión que sigue arriba y
    no se puede volver a pesar hasta que el indicador baje a umbral_cero_kg o menos. Desde ahí vuelve a
    mostrar el peso real, que crece con el próximo camión hasta estabilizarse."""

    def __init__(self, umbral_cero_kg: float = 100):
        self.umbral_cero_kg = umbral_cero_kg
        self.en_cero = False

    def pesado(self) -> None:
        self.en_cero = True

    def filtrar(self, lectura: LecturaPeso) -> LecturaPeso:
        """Devuelve la lectura a mostrar: la real, o 0 kg (no estable) mientras espera que baje el camión."""
        if self.en_cero and lectura.kg <= self.umbral_cero_kg:
            self.en_cero = False
        if self.en_cero:
            return LecturaPeso(0, False, lectura.crudo, lectura.momento)
        return lectura
