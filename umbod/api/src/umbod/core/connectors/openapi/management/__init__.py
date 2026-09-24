from importlib import import_module
from typing import Any

__all__ = [
    "ActivationPermissionChangeGuard",
    "AllowActivationPermissionChangeGuard",
    "CreateOpenApiConnector",
    "ImportOpenApiCatalog",
    "OpenApiBearerConfiguration",
    "OpenApiClock",
    "OpenApiConfigurationAdapter",
    "OpenApiConfigurationPort",
    "OpenApiConfigurationStatus",
    "OpenApiConnector",
    "OpenApiConnectorCatalog",
    "OpenApiConnectorManagementService",
    "OpenApiCurrentCatalogImportService",
    "OpenApiIdGenerator",
    "OpenApiServerSelectionRequired",
    "PersistedGroupPermissionActivationChangeGuard",
    "ReplaceCurrentOpenApiCatalog",
    "compose_openapi_connector_management",
]

_EXPORTS: dict[str, str] = {
    "ActivationPermissionChangeGuard": ".current_catalog_import",
    "AllowActivationPermissionChangeGuard": ".current_catalog_import",
    "CreateOpenApiConnector": ".models",
    "ImportOpenApiCatalog": ".models",
    "OpenApiBearerConfiguration": ".configuration",
    "OpenApiClock": ".current_catalog_import",
    "OpenApiConfigurationAdapter": ".configuration",
    "OpenApiConfigurationPort": ".configuration",
    "OpenApiConfigurationStatus": ".configuration",
    "OpenApiConnector": ".models",
    "OpenApiConnectorCatalog": ".models",
    "OpenApiConnectorManagementService": ".service",
    "OpenApiCurrentCatalogImportService": ".current_catalog_import",
    "OpenApiIdGenerator": ".current_catalog_import",
    "OpenApiServerSelectionRequired": "umbod.core.connectors.openapi.importing.preparation",
    "PersistedGroupPermissionActivationChangeGuard": ".permission_change_guard",
    "ReplaceCurrentOpenApiCatalog": ".models",
    "compose_openapi_connector_management": ".service",
}


def __getattr__(name: str) -> Any:
    module_name = _EXPORTS.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    if module_name.startswith("."):
        value = getattr(import_module(module_name, __name__), name)
    else:
        value = getattr(import_module(module_name), name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(__all__)
