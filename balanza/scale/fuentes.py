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


RANGO_TARA = (13_800, 14_500)  # camión vacío
RANGO_BRUTO = (44_000, 45_000)  # camión cargado
RANGOS = {"TARA": RANGO_TARA, "BRUTO": RANGO_BRUTO}


class FuenteSimulada:
    """Simula la balanza: vacía hasta que se pide subir un camión (al consultar el CTG), que se estabiliza
    con un peso de tara o de bruto y queda quieto hasta que se pide que baje (después de pesar)."""

    descripcion = "Simulador"

    def __init__(self, intervalo_s: float = 0.2, semilla: int | None = None, division_kg: int = 20):
        self.intervalo_s = intervalo_s
        self.division_kg = division_kg
        self._rng = random.Random(semilla)
        self._pesos: Iterator[tuple[int, bool]] | None = None
        # Los pide el hilo de la pantalla; el ciclo los lee en cada lectura.
        self._objetivo: int | None = None  # peso del camión pedido, None = balanza vacía
        self._pedido = 0  # cambia con cada subir/bajar

    def subir(self, tipo: str) -> None:
        """Sube un camión con peso de "TARA" o "BRUTO" (si había otro arriba, primero baja)."""
        minimo, maximo = RANGOS[tipo]
        d = self.division_kg
        # Una división adentro de cada extremo: la oscilación del indicador no sale del rango.
        self._objetivo = self._rng.randrange(minimo + d, maximo - d + 1, d)
        self._pedido += 1

    def bajar(self) -> None:
        self._objetivo = None
        self._pedido += 1

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
            pedido, objetivo = self._pedido, self._objetivo
            if objetivo is None:  # balanza vacía
                yield 0, True
                continue
            for i in range(1, 11):  # sube el camión
                yield redondear(objetivo * i / 10 + rng.uniform(-400, 400)), False
            for _ in range(8):  # se acomoda
                yield redondear(objetivo + rng.uniform(-3 * d, 3 * d)), False
            while self._pedido == pedido:  # quieto hasta que se pese; oscila a lo sumo una división
                yield objetivo + rng.choice([0, 0, 0, d, -d]), True
            for i in range(9, 0, -1):  # baja
                yield max(0, redondear(objetivo * i / 10 + rng.uniform(-400, 400))), False
            for _ in range(5):  # vacía un momento antes del próximo
                yield 0, True
