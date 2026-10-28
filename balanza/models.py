"""Entidades del dominio."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum


class Operacion(StrEnum):
    DESCARGA = "descarga"  # entra cargado, sale vacío
    CARGA = "carga"  # entra vacío, sale cargado


class EstadoPesaje(StrEnum):
    ABIERTO = "abierto"  # tiene solo el primer peso
    CERRADO = "cerrado"  # tiene los dos pesos


@dataclass
class Camion:
    id: str  # en LogiGrain, el número de CTG de la Carta de Porte
    patente: str
    operacion: Operacion = Operacion.DESCARGA
    patente_acoplado: str = ""
    chofer: str = ""
    transportista: str = ""
    producto: str = ""
    destinatario: str = ""
    turno: str = ""
    posicion: str = ""  # código de LogiGrain, ej. EN_PUERTO_CALADO / CON_PRIMER_PESO
    posicion_label: str = ""
    primer_peso_kg: float | None = None  # 1° peso ya registrado en LogiGrain (quizás en otra balanza)
    primer_peso_momento: datetime | None = None
    primer_peso_balanza_nro: int | None = None
    chofer_cuit: str = ""
    fecha_ingreso: datetime | None = None  # llegada al puerto
    cpe_id: int | None = None  # id de la CPE en LogiGrain
    grado: str = ""  # grado de calada
    datos: dict = field(default_factory=dict)  # respuesta original de la API


@dataclass(frozen=True)
class LecturaPeso:
    kg: float
    estable: bool
    crudo: str  # línea tal cual llegó del indicador (auditoría)
    momento: datetime = field(default_factory=datetime.now)


@dataclass
class Pesaje:
    id: int | None
    camion_id: str
    patente: str
    operacion: Operacion
    puesto: str
    peso1_kg: float
    peso1_momento: datetime
    peso1_crudo: str = ""
    peso2_kg: float | None = None
    peso2_momento: datetime | None = None
    peso2_crudo: str = ""
    patente_acoplado: str = ""
    producto: str = ""
    chofer: str = ""
    transportista: str = ""
    destinatario: str = ""
    balanza1_nro: int | None = None  # balanza en la que se tomó cada peso
    balanza2_nro: int | None = None
    romaneo: dict | None = None  # respuesta de LogiGrain al 2° peso: neto, mermas y neto final
    # Datos de la Carta de Porte y del puesto que van en el ticket.
    chofer_cuit: str = ""
    fecha_ingreso: datetime | None = None  # llegada al puerto según LogiGrain
    cpe_id: int | None = None  # id de la CPE en LogiGrain: "Código" del ticket
    grado: str = ""  # grado de calada
    operador: str = ""  # usuario de LogiGrain que tomó el último peso
    simulado: bool = False  # algún peso vino del simulador y no del indicador

    @property
    def estado(self) -> EstadoPesaje:
        return EstadoPesaje.ABIERTO if self.peso2_kg is None else EstadoPesaje.CERRADO

    @property
    def numero(self) -> str:
        return f"{self.puesto}-{self.id:06d}"

    # Bruto/tara por máximo/mínimo: vale para descarga (entra cargado) y carga (entra vacío).
    @property
    def bruto_kg(self) -> float | None:
        return None if self.peso2_kg is None else max(self.peso1_kg, self.peso2_kg)

    @property
    def tara_kg(self) -> float | None:
        return None if self.peso2_kg is None else min(self.peso1_kg, self.peso2_kg)

    @property
    def neto_kg(self) -> float | None:
        return None if self.peso2_kg is None else self.bruto_kg - self.tara_kg

    def a_payload(self, evento: str) -> dict:
        """Datos que se envían a la API. `id_local` permite a la API descartar reenvíos duplicados."""
        return {
            "evento": evento,
            "id_local": self.numero,
            "balanza_nro": self.balanza1_nro if evento == "primer_peso" else self.balanza2_nro,
            "camion_id": self.camion_id,
            "patente": self.patente,
            "operacion": str(self.operacion),
            "puesto": self.puesto,
            "peso1_kg": self.peso1_kg,
            "peso1_momento": self.peso1_momento.isoformat(timespec="seconds"),
            "peso2_kg": self.peso2_kg,
            "peso2_momento": self.peso2_momento.isoformat(timespec="seconds") if self.peso2_momento else None,
            "bruto_kg": self.bruto_kg,
            "tara_kg": self.tara_kg,
            "neto_kg": self.neto_kg,
        }


@dataclass
class Envio:
    """Evento pendiente de enviar a la API (cola local)."""

    id: int
    pesaje_id: int
    tipo: str
    payload: dict
    intentos: int
    ultimo_error: str
