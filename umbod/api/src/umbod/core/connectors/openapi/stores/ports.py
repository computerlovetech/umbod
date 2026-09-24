from typing import Optional, Protocol

from umbod.core.connectors.openapi.stores.catalog_models import (
    OpenApiCatalogHeader,
    OpenApiOperationSummary,
    PersistedOpenApiOperation,
)

from umbod.core.connectors.openapi.management.models import (
    OpenApiConnector,
    OpenApiConnectorCatalog,
    ReplaceCurrentOpenApiCatalog,
)
class OpenApiConnectorReader(Protocol):
    async def get_connector(self, connector_id: str) -> OpenApiConnector: ...

    async def list_connectors(self) -> tuple[OpenApiConnector, ...]: ...


class OpenApiConnectorWriter(Protocol):
    async def save_connector(self, connector: OpenApiConnector) -> None: ...

    async def delete_connector(self, connector_id: str) -> None: ...


class AtomicCurrentOpenApiCatalogWriter(Protocol):
    async def replace_current_catalog(
        self, replacement: ReplaceCurrentOpenApiCatalog
    ) -> OpenApiConnectorCatalog: ...


class CurrentOpenApiCatalogHeaderReader(Protocol):
    async def read_current_catalog_header(self, connector_id: str) -> Optional[OpenApiCatalogHeader]: ...

    async def current_catalog_exists(self, connector_id: str) -> bool: ...

    async def current_catalog_connector_ids(self, connector_ids: tuple[str, ...]) -> frozenset[str]: ...


class OpenApiOperationSummaryReader(Protocol):
    async def list_operation_summaries(
        self, connector_id: str
    ) -> tuple[OpenApiOperationSummary, ...]: ...


class OpenApiOperationReader(Protocol):
    async def read_operation(
        self, connector_id: str, operation_id: str
    ) -> Optional[PersistedOpenApiOperation]: ...


class CurrentOpenApiCatalogReader(Protocol):
    async def read_current_catalog(self, connector_id: str) -> Optional[OpenApiConnectorCatalog]: ...


class OpenApiConnectorStore(
    OpenApiConnectorReader,
    OpenApiConnectorWriter,
    AtomicCurrentOpenApiCatalogWriter,
    CurrentOpenApiCatalogReader,
    CurrentOpenApiCatalogHeaderReader,
    OpenApiOperationSummaryReader,
    OpenApiOperationReader,
    Protocol,
):
    async def save_catalog(self, catalog: OpenApiConnectorCatalog) -> None: ...


__all__ = [
    "AtomicCurrentOpenApiCatalogWriter",
    "CurrentOpenApiCatalogHeaderReader",
    "CurrentOpenApiCatalogReader",
    "OpenApiConnectorReader",
    "OpenApiOperationReader",
    "OpenApiOperationSummaryReader",
    "OpenApiConnectorStore",
    "OpenApiConnectorWriter",
]
