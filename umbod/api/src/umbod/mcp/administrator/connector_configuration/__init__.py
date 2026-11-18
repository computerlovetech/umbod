from importlib import import_module
from typing import Any

__all__ = [
    "AdministratorConfigurationCatalog",
    "AdministratorConnectorConfigurationTools",
    "configuration_rejection_error",
    "register_administrator_connector_configuration_tools",
]

_EXPORTS: dict[str, str] = {
    "AdministratorConfigurationCatalog": ".catalog",
    "AdministratorConnectorConfigurationTools": ".tools",
    "configuration_rejection_error": ".errors",
    "register_administrator_connector_configuration_tools": ".registration",
}


def __getattr__(name: str) -> Any:
    module_name = _EXPORTS.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(import_module(module_name, __name__), name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(__all__)
