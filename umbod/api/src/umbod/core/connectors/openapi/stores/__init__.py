from importlib import import_module
from typing import Any

__all__ = [
    "AtomicCurrentOpenApiCatalogWriter",
    "CATALOG_OPERATION_TABLE",
    "CATALOG_SOURCE_TABLE",
    "CONNECTOR_TABLE",
    "CURRENT_CATALOG_HEADER_TABLE",
    "CurrentOpenApiCatalogHeaderReader",
    "CurrentOpenApiCatalogReader",
    "OpenApiCatalogHeader",
    "OpenApiConnectorReader",
    "OpenApiConnectorStore",
    "OpenApiConnectorStoreService",
    "OpenApiConnectorWriter",
    "OpenApiOperationReader",
    "OpenApiOperationSummary",
    "OpenApiOperationSummaryReader",
    "PersistedOpenApiOperation",
]

_EXPORTS: dict[str, str] = {
    "AtomicCurrentOpenApiCatalogWriter": ".ports",
    "CATALOG_OPERATION_TABLE": ".schema",
    "CATALOG_SOURCE_TABLE": ".schema",
    "CONNECTOR_TABLE": ".schema",
    "CURRENT_CATALOG_HEADER_TABLE": ".schema",
    "CurrentOpenApiCatalogHeaderReader": ".ports",
    "CurrentOpenApiCatalogReader": ".ports",
    "OpenApiCatalogHeader": ".catalog_models",
    "OpenApiConnectorReader": ".ports",
    "OpenApiConnectorStore": ".ports",
    "OpenApiConnectorStoreService": ".service",
    "OpenApiConnectorWriter": ".ports",
    "OpenApiOperationReader": ".ports",
    "OpenApiOperationSummary": ".catalog_models",
    "OpenApiOperationSummaryReader": ".ports",
    "PersistedOpenApiOperation": ".catalog_models",
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
