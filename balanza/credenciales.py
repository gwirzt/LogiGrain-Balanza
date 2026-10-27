"""Lectura del archivo .env con las credenciales de LogiGrain."""
from __future__ import annotations

from pathlib import Path

VAR_USUARIO = "USUARIO_LOGIGRAIN"
VAR_CONTRASENA = "CONTRASENA_LOGIGRAIN"


def leer_env(ruta: str | Path) -> dict[str, str]:
    """Formato CLAVE=valor, una por línea. Ignora comentarios (#) y comillas alrededor del valor.
    Si el archivo no existe devuelve un diccionario vacío."""
    ruta = Path(ruta)
    if not ruta.exists():
        return {}
    valores = {}
    for linea in ruta.read_text(encoding="utf-8-sig").splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#") or "=" not in linea:
            continue
        clave, valor = linea.split("=", 1)
        valor = valor.strip()
        if len(valor) >= 2 and valor[0] == valor[-1] and valor[0] in "\"'":
            valor = valor[1:-1]
        valores[clave.strip()] = valor
    return valores
