"""Carga de configuración desde config.toml."""
from __future__ import annotations

import tomllib
from dataclasses import dataclass, field, fields
from pathlib import Path

MAX_BALANZAS = 2
MODOS_BALANZA = ("simulador", "serie")


@dataclass
class BalanzaConfig:
    """Un cabezal (indicador). La primera balanza del archivo se muestra a la izquierda, la segunda a la derecha."""

    nro: int = 1  # número de balanza en LogiGrain (se envía como balanza_nro)
    modo: str = "simulador"  # modo al abrir: "simulador" | "serie" (se cambia en pantalla con Ctrl+F2/F3)
    puerto: str = "COM1"
    baudios: int = 9600
    bits_datos: int = 8
    paridad: str = "N"  # N, E, O
    bits_parada: int = 1
    protocolo: str = "generico"
    division_kg: int = 20  # mínima unidad que muestra el indicador (celdas de camiones: 20 kg)
    umbral_cero_kg: float = 100  # después de pesar, vuelve a leer cuando el indicador baja a este valor
    lecturas_estables: int = 5
    tolerancia_kg: float = 20.0


@dataclass
class ApiConfig:
    modo: str = "mock"  # "mock" | "http"
    url_base: str = ""
    port_id: int | None = None  # sin valor: el primer puerto asignado al usuario
    enviar_pesos: bool = False  # seguridad: hasta habilitarlo no se registran pesos en LogiGrain
    permitir_pesos_simulados: bool = False  # solo para pruebas: deja enviar a LogiGrain los pesos del simulador
    timeout_s: float = 10.0
    intervalo_sync_s: int = 30

    @property
    def envia_pesos_simulados(self) -> bool:
        """True si un peso del simulador terminaría registrado en LogiGrain."""
        return self.modo == "http" and self.enviar_pesos

    @property
    def simulador_permitido(self) -> bool:
        return self.permitir_pesos_simulados or not self.envia_pesos_simulados


@dataclass
class TicketConfig:
    impresora: str = ""  # vacío = impresora predeterminada de Windows
    ancho_mm: int = 80
    alto_mm: int = 200
    empresa: str = "Logiports"
    vista_previa: bool = True
    guardar_pdf: bool = True  # copia PDF de cada ticket en <carpeta_datos>/tickets/AAAA-MM/


@dataclass
class AppConfig:
    puesto: str = "BALANZA-1"
    carpeta_datos: str = "datos"
    peso_minimo_kg: float = 500.0  # no permite capturar pesos menores (balanza vacía)
    balanzas: list[BalanzaConfig] = field(default_factory=lambda: [BalanzaConfig()])
    api: ApiConfig = field(default_factory=ApiConfig)
    ticket: TicketConfig = field(default_factory=TicketConfig)

    @property
    def ruta_db(self) -> Path:
        return Path(self.carpeta_datos) / "balanza.db"

    @property
    def carpeta_tickets(self) -> Path:
        return Path(self.carpeta_datos) / "tickets"


def _armar(cls, datos: dict, seccion: str):
    validos = {f.name for f in fields(cls)}
    desconocidos = set(datos) - validos
    if desconocidos:
        raise ValueError(f"Claves desconocidas en [{seccion}]: {', '.join(sorted(desconocidos))}")
    return cls(**datos)


def _balanzas(datos: dict) -> list[BalanzaConfig]:
    if "balanzas" in datos and "balanza" in datos:
        raise ValueError("Use [[balanzas]] (una por cabezal) o [balanza], no ambos.")
    if "balanza" in datos:  # formato anterior: un solo cabezal
        lista = [_armar(BalanzaConfig, datos["balanza"], "balanza")]
    else:
        lista = [_armar(BalanzaConfig, b, "balanzas") for b in datos.get("balanzas", [{}])]
    if not 1 <= len(lista) <= MAX_BALANZAS:
        raise ValueError(f"Se admiten 1 o {MAX_BALANZAS} balanzas; hay {len(lista)}.")
    for b in lista:
        if b.modo not in MODOS_BALANZA:
            raise ValueError(f"Modo de balanza desconocido: {b.modo!r} (use 'simulador' o 'serie').")
    nros = [b.nro for b in lista]
    if len(set(nros)) != len(nros):
        raise ValueError(f"Cada balanza necesita un nro distinto (están repetidos: {nros}).")
    return lista


def cargar_config(ruta: str | Path | None = None) -> AppConfig:
    """Lee el archivo TOML. Sin ruta devuelve la configuración por defecto (simulador + API de prueba).
    Lanza ValueError (o tomllib.TOMLDecodeError) con un mensaje para mostrar si el archivo tiene errores."""
    if ruta is None:
        return AppConfig()
    with open(ruta, "rb") as f:
        datos = tomllib.load(f)
    if "balanza_nro" in datos.get("api", {}):
        raise ValueError("balanza_nro ya no va en [api]: cada bloque [[balanzas]] lleva su propio nro.")
    kwargs = {k: v for k, v in datos.items() if k not in ("balanza", "balanzas", "api", "ticket")}
    kwargs["balanzas"] = _balanzas(datos)
    kwargs["api"] = _armar(ApiConfig, datos.get("api", {}), "api")
    kwargs["ticket"] = _armar(TicketConfig, datos.get("ticket", {}), "ticket")
    return _armar(AppConfig, kwargs, "general")
