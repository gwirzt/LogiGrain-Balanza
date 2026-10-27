from ..config import ApiConfig
from .cliente import ClienteLogigrain, ErrorApi, ErrorAutenticacion


def crear_cliente(cfg: ApiConfig) -> ClienteLogigrain:
    if cfg.modo == "mock":
        from .mock import ClienteMock

        return ClienteMock()
    if cfg.modo == "http":
        from .cliente import ClienteHttp

        return ClienteHttp(cfg)
    raise ValueError(f"Modo de API desconocido: {cfg.modo!r} (use 'mock' o 'http')")


__all__ = ["ClienteLogigrain", "ErrorApi", "ErrorAutenticacion", "crear_cliente"]
