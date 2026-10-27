"""Punto de entrada: python -m balanza [--config config.toml]"""
from __future__ import annotations

import argparse
import logging
import sys
import tomllib
from logging.handlers import RotatingFileHandler
from pathlib import Path

from .config import cargar_config

log = logging.getLogger("balanza")


def configurar_logs(carpeta: Path) -> None:
    carpeta.mkdir(parents=True, exist_ok=True)
    formato = logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s")
    archivo = RotatingFileHandler(carpeta / "balanza.log", maxBytes=2_000_000, backupCount=5, encoding="utf-8")
    archivo.setFormatter(formato)
    manejadores: list[logging.Handler] = [archivo]
    if sys.stderr is not None:  # el .exe sin consola no tiene stderr
        consola = logging.StreamHandler()
        consola.setFormatter(formato)
        manejadores.append(consola)
    logging.basicConfig(level=logging.INFO, handlers=manejadores)


def carpeta_base() -> Path:
    """Carpeta del .exe si está empaquetado; si no, el directorio actual."""
    return Path(sys.executable).parent if getattr(sys, "frozen", False) else Path.cwd()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="balanza", description="Puesto de balanza Logigrain")
    ap.add_argument("--config", default="config.toml", help="archivo de configuración (default: config.toml)")
    args = ap.parse_args(argv)

    base = carpeta_base()
    ruta = base / args.config
    try:
        cfg = cargar_config(ruta if ruta.exists() else None)
    except (ValueError, tomllib.TOMLDecodeError) as e:
        from PySide6.QtWidgets import QApplication, QMessageBox

        app = QApplication(sys.argv)
        QMessageBox.critical(None, "Error en config.toml", f"{ruta}\n\n{e}")
        return 1
    cfg.carpeta_datos = str(base / cfg.carpeta_datos)
    configurar_logs(Path(cfg.carpeta_datos))
    if not ruta.exists():
        log.warning("No se encontró %s: se usa la configuración por defecto (simulador + API de prueba).", ruta)

    from PySide6.QtGui import QPalette
    from PySide6.QtWidgets import QApplication, QMessageBox

    from .api import crear_cliente
    from .credenciales import VAR_CONTRASENA, VAR_USUARIO, leer_env
    from .services.pesaje import ServicioPesaje
    from .services.sync import Sincronizador
    from .storage.db import BaseDatos
    from .ui.login import DialogoLogin
    from .ui.ventana import VentanaPrincipal

    app = QApplication(sys.argv)
    app.setApplicationName("Balanza Logigrain")
    app.setStyle("Fusion")
    paleta = app.palette()  # filas alternadas en un tono neutro (Windows usa el color de acento)
    fondo = paleta.color(QPalette.ColorRole.Base)
    paleta.setColor(QPalette.ColorRole.AlternateBase, fondo.lighter(125) if fondo.lightness() < 128 else fondo.darker(105))
    app.setPalette(paleta)

    def error_no_controlado(tipo, valor, traza):
        log.critical("Error no controlado", exc_info=(tipo, valor, traza))
        QMessageBox.critical(None, "Error inesperado", f"{valor}\n\nEl detalle quedó en el log.")

    sys.excepthook = error_no_controlado

    simuladas = [str(b.nro) for b in cfg.balanzas if b.modo == "simulador"]
    if cfg.api.modo == "http" and cfg.api.enviar_pesos and simuladas:
        QMessageBox.critical(
            None, "Configuración insegura",
            f"La balanza {', '.join(simuladas)} está en modo simulador y enviar_pesos = true:\n"
            "se registrarían pesos ficticios en LogiGrain.\n\n"
            "Ponga modo = \"serie\" en cada balanza o enviar_pesos = false.",
        )
        return 1

    db = BaseDatos(cfg.ruta_db)
    cliente = crear_cliente(cfg.api)
    if cliente.requiere_login:
        credenciales = leer_env(base / ".env")
        dialogo = DialogoLogin(
            cliente, cfg.api.url_base, credenciales.get(VAR_USUARIO, ""), credenciales.get(VAR_CONTRASENA, "")
        )
        if dialogo.exec() != DialogoLogin.DialogCode.Accepted:
            return 0

    ventana = VentanaPrincipal(
        cfg,
        db,
        cliente,
        ServicioPesaje(db, cfg.puesto, cfg.peso_minimo_kg),
        Sincronizador(db, cliente),
    )
    ventana.showMaximized()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
