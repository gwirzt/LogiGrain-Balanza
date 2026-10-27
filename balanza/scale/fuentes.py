"""Fuentes de líneas de texto del indicador: puerto serie real o simulador."""
from __future__ import annotations

import random
import time
from collections.abc import Iterator

from ..config import BalanzaConfig


class FuenteSerie:
    def __init__(self, cfg: BalanzaConfig):
        self.cfg = cfg
        self._puerto = None

    @property
    def descripcion(self) -> str:
        return f"{self.cfg.puerto} {self.cfg.baudios} {self.cfg.bits_datos}{self.cfg.paridad}{self.cfg.bits_parada}"

    def abrir(self) -> None:
        import serial

        self._puerto = serial.Serial(
            port=self.cfg.puerto,
            baudrate=self.cfg.baudios,
            bytesize=self.cfg.bits_datos,
            parity=self.cfg.paridad,
            stopbits=self.cfg.bits_parada,
            timeout=1,
        )

    def leer_linea(self) -> str | None:
        """Devuelve una línea o None si no llegó nada en el timeout."""
        crudo = self._puerto.readline()
        return crudo.decode("ascii", errors="replace").strip() or None

    def cerrar(self) -> None:
        if self._puerto is not None:
            self._puerto.close()
            self._puerto = None


class FuenteSimulada:
    """Simula camiones que suben a la balanza, se estabilizan y bajan, en ciclo."""

    descripcion = "Simulador"

    def __init__(self, intervalo_s: float = 0.2, semilla: int | None = None, division_kg: int = 20):
        self.intervalo_s = intervalo_s
        self.division_kg = division_kg
        self._rng = random.Random(semilla)
        self._pesos: Iterator[tuple[int, bool]] | None = None

    def abrir(self) -> None:
        self._pesos = self._ciclo()

    def leer_linea(self) -> str | None:
        time.sleep(self.intervalo_s)
        kg, quieto = next(self._pesos)
        return f"{'ST' if quieto else 'US'},GS,{kg:+07d}kg"

    def cerrar(self) -> None:
        self._pesos = None

    def _ciclo(self) -> Iterator[tuple[int, bool]]:
        rng = self._rng
        d = self.division_kg

        def redondear(x: float) -> int:  # el indicador muestra múltiplos de la división
            return int(round(x / d) * d)

        while True:
            for _ in range(15):  # balanza vacía
                yield 0, True
            objetivo = rng.choice([rng.randint(13_000, 17_000), rng.randint(40_000, 52_000)])  # tara o cargado
            for i in range(1, 11):  # sube el camión
                yield redondear(objetivo * i / 10 + rng.uniform(-400, 400)), False
            for _ in range(8):  # se acomoda
                yield redondear(objetivo + rng.uniform(-3 * d, 3 * d)), False
            for _ in range(150):  # quieto ~30 s (tiempo para consultar el CTG y pesar), oscila a lo sumo una división
                yield redondear(objetivo) + rng.choice([0, 0, 0, d, -d]), True
            for i in range(9, -1, -1):  # baja
                yield max(0, redondear(objetivo * i / 10 + rng.uniform(-400, 400))), False


def crear_fuente(cfg: BalanzaConfig):
    if cfg.modo == "simulador":
        return FuenteSimulada(division_kg=cfg.division_kg)
    if cfg.modo == "serie":
        return FuenteSerie(cfg)
    raise ValueError(f"Modo de balanza desconocido: {cfg.modo!r} (use 'simulador' o 'serie')")
