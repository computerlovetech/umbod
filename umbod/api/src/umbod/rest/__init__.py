from importlib import import_module
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from umbod.rest.main import create_app
    from umbod.rest.settings import APISettings

__all__ = ["APISettings", "create_app"]

_EXPORTS: dict[str, str] = {
    "APISettings": ".settings",
    "create_app": ".main",
}


def __getattr__(name: str) -> Any:
    module_name = _EXPORTS.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name}")
    value = getattr(import_module(module_name, __name__), name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(__all__)
