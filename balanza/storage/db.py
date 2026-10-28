"""Base SQLite local: pesajes y cola de envíos a la API.

Cada pesaje y su evento de envío se graban en la misma transacción, así nunca queda
un peso registrado sin su envío pendiente (ni al revés), aunque se corte la luz o internet.
"""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from dataclasses import replace
from datetime import datetime
from pathlib import Path

from ..models import Envio, Operacion, Pesaje

ESQUEMA = """
CREATE TABLE IF NOT EXISTS pesajes (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    camion_id        TEXT NOT NULL,
    patente          TEXT NOT NULL,
    patente_acoplado TEXT NOT NULL DEFAULT '',
    operacion        TEXT NOT NULL,
    puesto           TEXT NOT NULL,
    producto         TEXT NOT NULL DEFAULT '',
    chofer           TEXT NOT NULL DEFAULT '',
    transportista    TEXT NOT NULL DEFAULT '',
    destinatario     TEXT NOT NULL DEFAULT '',
    peso1_kg         REAL NOT NULL,
    peso1_momento    TEXT NOT NULL,
    peso1_crudo      TEXT NOT NULL DEFAULT '',
    peso2_kg         REAL,
    peso2_momento    TEXT,
    peso2_crudo      TEXT NOT NULL DEFAULT '',
    balanza1_nro     INTEGER,
    balanza2_nro     INTEGER,
    romaneo          TEXT,
    chofer_cuit      TEXT NOT NULL DEFAULT '',
    fecha_ingreso    TEXT,
    cpe_id           INTEGER,
    grado            TEXT NOT NULL DEFAULT '',
    operador         TEXT NOT NULL DEFAULT '',
    simulado         INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS ix_pesajes_camion ON pesajes (camion_id, peso2_kg);
CREATE INDEX IF NOT EXISTS ix_pesajes_momento ON pesajes (peso1_momento);

CREATE TABLE IF NOT EXISTS envios (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    pesaje_id    INTEGER NOT NULL REFERENCES pesajes (id),
    tipo         TEXT NOT NULL,
    payload      TEXT NOT NULL,
    creado       TEXT NOT NULL,
    intentos     INTEGER NOT NULL DEFAULT 0,
    ultimo_error TEXT NOT NULL DEFAULT '',
    enviado      TEXT
);
CREATE INDEX IF NOT EXISTS ix_envios_pendientes ON envios (enviado);
"""

# Columnas agregadas después de la primera versión: se suman a bases ya existentes.
MIGRACIONES = {
    "pesajes": {"destinatario": "TEXT NOT NULL DEFAULT ''", "balanza1_nro": "INTEGER", "balanza2_nro": "INTEGER",
                "romaneo": "TEXT", "chofer_cuit": "TEXT NOT NULL DEFAULT ''", "fecha_ingreso": "TEXT",
                "cpe_id": "INTEGER", "grado": "TEXT NOT NULL DEFAULT ''", "operador": "TEXT NOT NULL DEFAULT ''",
                "simulado": "INTEGER NOT NULL DEFAULT 0"},
}


def _fecha(valor: str | None) -> datetime | None:
    return datetime.fromisoformat(valor) if valor else None


def _a_pesaje(r: sqlite3.Row) -> Pesaje:
    return Pesaje(
        id=r["id"],
        camion_id=r["camion_id"],
        patente=r["patente"],
        patente_acoplado=r["patente_acoplado"],
        operacion=Operacion(r["operacion"]),
        puesto=r["puesto"],
        producto=r["producto"],
        chofer=r["chofer"],
        transportista=r["transportista"],
        destinatario=r["destinatario"],
        peso1_kg=r["peso1_kg"],
        peso1_momento=_fecha(r["peso1_momento"]),
        peso1_crudo=r["peso1_crudo"],
        peso2_kg=r["peso2_kg"],
        peso2_momento=_fecha(r["peso2_momento"]),
        peso2_crudo=r["peso2_crudo"],
        balanza1_nro=r["balanza1_nro"],
        balanza2_nro=r["balanza2_nro"],
        romaneo=json.loads(r["romaneo"]) if r["romaneo"] else None,
        chofer_cuit=r["chofer_cuit"],
        fecha_ingreso=_fecha(r["fecha_ingreso"]),
        cpe_id=r["cpe_id"],
        grado=r["grado"],
        operador=r["operador"],
        simulado=bool(r["simulado"]),
    )


class BaseDatos:
    def __init__(self, ruta: str | Path):
        self.ruta = Path(ruta)
        self.ruta.parent.mkdir(parents=True, exist_ok=True)
        with self._conectar() as cx:
            cx.executescript(ESQUEMA)
            for tabla, columnas in MIGRACIONES.items():
                existentes = {r["name"] for r in cx.execute(f"PRAGMA table_info({tabla})")}
                for columna, definicion in columnas.items():
                    if columna not in existentes:
                        cx.execute(f"ALTER TABLE {tabla} ADD COLUMN {columna} {definicion}")

    @contextmanager
    def _conectar(self):
        # Una conexión por operación: se puede usar desde el hilo de sincronización sin compartir conexiones.
        cx = sqlite3.connect(self.ruta, timeout=10)
        cx.row_factory = sqlite3.Row
        cx.execute("PRAGMA journal_mode=WAL")
        cx.execute("PRAGMA foreign_keys=ON")
        try:
            yield cx
            cx.commit()
        except BaseException:
            cx.rollback()
            raise
        finally:
            cx.close()

    # --- Pesajes ---------------------------------------------------------------

    def insertar_pesaje(self, p: Pesaje, evento: str | None) -> Pesaje:
        """`evento` None: el 1° peso ya está en la API (tomado en otra balanza) y no se vuelve a enviar."""
        with self._conectar() as cx:
            cur = cx.execute(
                """INSERT INTO pesajes (camion_id, patente, patente_acoplado, operacion, puesto, producto, chofer,
                                        transportista, destinatario, peso1_kg, peso1_momento, peso1_crudo, balanza1_nro,
                                        chofer_cuit, fecha_ingreso, cpe_id, grado, operador, simulado)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (p.camion_id, p.patente, p.patente_acoplado, str(p.operacion), p.puesto, p.producto, p.chofer,
                 p.transportista, p.destinatario, p.peso1_kg, p.peso1_momento.isoformat(), p.peso1_crudo,
                 p.balanza1_nro, p.chofer_cuit, p.fecha_ingreso.isoformat() if p.fecha_ingreso else None,
                 p.cpe_id, p.grado, p.operador, int(p.simulado)),
            )
            p = replace(p, id=cur.lastrowid)
            if evento:
                self._encolar(cx, p, evento)
        return p

    def registrar_segundo_peso(self, p: Pesaje, evento: str) -> Pesaje:
        with self._conectar() as cx:
            cur = cx.execute(
                """UPDATE pesajes SET peso2_kg = ?, peso2_momento = ?, peso2_crudo = ?, balanza2_nro = ?,
                                     operador = ?, simulado = ?
                   WHERE id = ? AND peso2_kg IS NULL""",
                (p.peso2_kg, p.peso2_momento.isoformat(), p.peso2_crudo, p.balanza2_nro, p.operador,
                 int(p.simulado), p.id),
            )
            if cur.rowcount != 1:
                raise RuntimeError(f"El pesaje {p.id} no existe o ya estaba cerrado.")
            self._encolar(cx, p, evento)
        return p

    def guardar_romaneo(self, pesaje_id: int, romaneo: dict) -> None:
        with self._conectar() as cx:
            cx.execute("UPDATE pesajes SET romaneo = ? WHERE id = ?", (json.dumps(romaneo), pesaje_id))

    def pesaje_abierto(self, camion_id: str) -> Pesaje | None:
        with self._conectar() as cx:
            r = cx.execute(
                "SELECT * FROM pesajes WHERE camion_id = ? AND peso2_kg IS NULL ORDER BY id DESC LIMIT 1",
                (camion_id,),
            ).fetchone()
        return _a_pesaje(r) if r else None

    def obtener_pesaje(self, pesaje_id: int) -> Pesaje | None:
        with self._conectar() as cx:
            r = cx.execute("SELECT * FROM pesajes WHERE id = ?", (pesaje_id,)).fetchone()
        return _a_pesaje(r) if r else None

    def pesajes_desde(self, desde: datetime) -> list[Pesaje]:
        with self._conectar() as cx:
            filas = cx.execute(
                "SELECT * FROM pesajes WHERE peso1_momento >= ? OR peso2_momento >= ? ORDER BY id DESC",
                (desde.isoformat(), desde.isoformat()),
            ).fetchall()
        return [_a_pesaje(r) for r in filas]

    # --- Cola de envíos --------------------------------------------------------

    @staticmethod
    def _encolar(cx: sqlite3.Connection, p: Pesaje, evento: str) -> None:
        cx.execute(
            "INSERT INTO envios (pesaje_id, tipo, payload, creado) VALUES (?, ?, ?, ?)",
            (p.id, evento, json.dumps(p.a_payload(evento)), datetime.now().isoformat()),
        )

    def envios_pendientes(self, limite: int = 50) -> list[Envio]:
        with self._conectar() as cx:
            filas = cx.execute(
                "SELECT * FROM envios WHERE enviado IS NULL ORDER BY id LIMIT ?", (limite,)
            ).fetchall()
        return [
            Envio(r["id"], r["pesaje_id"], r["tipo"], json.loads(r["payload"]), r["intentos"], r["ultimo_error"])
            for r in filas
        ]

    def marcar_enviado(self, envio_id: int) -> None:
        with self._conectar() as cx:
            cx.execute(
                "UPDATE envios SET enviado = ?, intentos = intentos + 1, ultimo_error = '' WHERE id = ?",
                (datetime.now().isoformat(), envio_id),
            )

    def marcar_error(self, envio_id: int, error: str) -> None:
        with self._conectar() as cx:
            cx.execute(
                "UPDATE envios SET intentos = intentos + 1, ultimo_error = ? WHERE id = ?",
                (error[:500], envio_id),
            )

    def envio_pendiente(self, pesaje_id: int, tipo: str) -> bool:
        with self._conectar() as cx:
            r = cx.execute(
                "SELECT 1 FROM envios WHERE pesaje_id = ? AND tipo = ? AND enviado IS NULL", (pesaje_id, tipo)
            ).fetchone()
        return r is not None

    def contar_pendientes(self) -> int:
        with self._conectar() as cx:
            return cx.execute("SELECT COUNT(*) FROM envios WHERE enviado IS NULL").fetchone()[0]

    def ultimo_error_envio(self) -> str:
        with self._conectar() as cx:
            r = cx.execute(
                "SELECT ultimo_error FROM envios WHERE enviado IS NULL AND ultimo_error <> '' ORDER BY id LIMIT 1"
            ).fetchone()
        return r[0] if r else ""
