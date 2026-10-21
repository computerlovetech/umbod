from importlib import import_module as _import_module
from types import ModuleType as _ModuleType
from typing import TYPE_CHECKING as _TYPE_CHECKING

if _TYPE_CHECKING:
    from umbod.mcp.connectors import downstream_mcp as downstream_mcp
    from umbod.mcp.connectors import native as native
    from umbod.mcp.connectors import openapi as openapi

__all__ = ["downstream_mcp", "native", "openapi"]


def __getattr__(name: str) -> _ModuleType:
    if name not in __all__:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module = _import_module(f".{name}", __name__)
    globals()[name] = module
    return module


def __dir__() -> list[str]:
    return sorted({*globals(), *__all__})
