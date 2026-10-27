"""Reglas de negocio de la captura de pesos."""
from __future__ import annotations

from datetime import datetime

from ..models import Camion, LecturaPeso, Pesaje
from ..storage.db import BaseDatos

EVENTO_PRIMER_PESO = "primer_peso"
EVENTO_SEGUNDO_PESO = "segundo_peso"
POSICION_CON_PRIMER_PESO = "CON_PRIMER_PESO"


class ErrorPesaje(Exception):
    """Validación que impide capturar el peso; el mensaje se muestra al operador."""


class ServicioPesaje:
    def __init__(self, db: BaseDatos, puesto: str, peso_minimo_kg: float, max_antiguedad_s: float = 3.0):
        self.db = db
        self.puesto = puesto
        self.peso_minimo_kg = peso_minimo_kg
        self.max_antiguedad_s = max_antiguedad_s

    def pesaje_abierto(self, camion: Camion) -> Pesaje | None:
        return self.db.pesaje_abierto(camion.id)

    def capturar(self, camion: Camion, lectura: LecturaPeso | None, balanza_nro: int | None = None) -> Pesaje:
        """Registra el primer peso del camión, o el segundo si ya tiene un pesaje abierto."""
        self._validar(lectura)
        abierto = self.db.pesaje_abierto(camion.id)
        if abierto is None and camion.posicion == POSICION_CON_PRIMER_PESO:
            # El 1° peso se tomó en otra balanza: se guarda como referencia (sin reenviarlo) y esta captura es el 2°.
            if camion.primer_peso_kg is None:
                raise ErrorPesaje("LogiGrain indica que el camión ya tiene 1° peso, pero no informa cuál es.")
            abierto = self.db.insertar_pesaje(
                self._nuevo(camion, camion.primer_peso_kg, camion.primer_peso_momento or datetime.now(),
                            "LogiGrain", camion.primer_peso_balanza_nro),
                evento=None,
            )
        if abierto is None:
            return self.db.insertar_pesaje(
                self._nuevo(camion, lectura.kg, lectura.momento, lectura.crudo, balanza_nro), EVENTO_PRIMER_PESO
            )

        abierto.peso2_kg = lectura.kg
        abierto.peso2_momento = lectura.momento
        abierto.peso2_crudo = lectura.crudo
        abierto.balanza2_nro = balanza_nro
        return self.db.registrar_segundo_peso(abierto, EVENTO_SEGUNDO_PESO)

    def _nuevo(self, camion: Camion, kg: float, momento: datetime, crudo: str, balanza_nro: int | None) -> Pesaje:
        return Pesaje(
            id=None,
            camion_id=camion.id,
            patente=camion.patente,
            patente_acoplado=camion.patente_acoplado,
            operacion=camion.operacion,
            puesto=self.puesto,
            producto=camion.producto,
            chofer=camion.chofer,
            transportista=camion.transportista,
            destinatario=camion.destinatario,
            peso1_kg=kg,
            peso1_momento=momento,
            peso1_crudo=crudo,
            balanza1_nro=balanza_nro,
        )

    def _validar(self, lectura: LecturaPeso | None) -> None:
        if lectura is None:
            raise ErrorPesaje("No hay lectura de la balanza.")
        if (datetime.now() - lectura.momento).total_seconds() > self.max_antiguedad_s:
            raise ErrorPesaje("La lectura de la balanza está desactualizada. Verifique la conexión con el indicador.")
        if not lectura.estable:
            raise ErrorPesaje("El peso no está estable. Espere a que se estabilice.")
        if lectura.kg < self.peso_minimo_kg:
            raise ErrorPesaje(
                f"El peso ({lectura.kg:,.0f} kg) es menor al mínimo permitido ({self.peso_minimo_kg:,.0f} kg)."
                .replace(",", ".")
            )
