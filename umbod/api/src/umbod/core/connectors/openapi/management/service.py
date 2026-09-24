from umbod.core.capabilities.tools.names import mangle_public_tool_name, normalize_tool_name_prefix
from umbod.core.connectors.openapi.management.current_catalog_import import (
    ActivationPermissionChangeGuard,
    AllowActivationPermissionChangeGuard,
    OpenApiClock,
    OpenApiCurrentCatalogImportService,
    OpenApiIdGenerator,
    OpenApiServerSelectionRequired,
)
from umbod.core.connectors.openapi.importing.preparation import DefaultOpenApiImportPreparer
from umbod.core.connectors.openapi.management.models import (
    CreateOpenApiConnector,
    ImportOpenApiCatalog,
    OpenApiConnector,
    OpenApiConnectorCatalog,
)
from umbod.core.connectors.openapi.stores import (
    OpenApiConnectorReader,
    OpenApiConnectorStore,
    OpenApiConnectorWriter,
)


class OpenApiConnectorManagementService:
    def __init__(
        self,
        connector_reader: OpenApiConnectorReader,
        connector_writer: OpenApiConnectorWriter,
        current_catalog_importer: OpenApiCurrentCatalogImportService,
        ids: OpenApiIdGenerator,
        clock: OpenApiClock,
    ) -> None:
        self._reader = connector_reader
        self._writer = connector_writer
        self._current_catalog_importer = current_catalog_importer
        self._ids = ids
        self._clock = clock

    async def create_connector(self, request: CreateOpenApiConnector) -> OpenApiConnector:
        display_name = request.display_name.strip()
        if not display_name:
            raise ValueError("Display name must not be empty")
        tool_name_prefix = normalize_tool_name_prefix(request.tool_name_prefix)
        mangle_public_tool_name(tool_name_prefix, "operation")
        timestamp = self._clock.now()
        connector = OpenApiConnector(
            connector_id=self._ids.new_id(),
            display_name=display_name,
            tool_name_prefix=tool_name_prefix,
            capability_description=request.capability_description,
            created_at=timestamp,
            updated_at=timestamp,
        )
        await self._writer.save_connector(connector)
        return connector

    async def delete_connector(self, connector_id: str) -> None:
        await self._reader.get_connector(connector_id)
        await self._writer.delete_connector(connector_id)

    async def import_catalog(self, request: ImportOpenApiCatalog) -> OpenApiConnectorCatalog:
        return await self._current_catalog_importer.import_current_catalog(request)

    async def list_connectors(self) -> tuple[OpenApiConnector, ...]:
        return await self._reader.list_connectors()

    async def get_connector(self, connector_id: str) -> OpenApiConnector:
        return await self._reader.get_connector(connector_id)


def compose_openapi_connector_management(
    store: OpenApiConnectorStore,
    ids: OpenApiIdGenerator,
    clock: OpenApiClock,
    permission_change_guard: ActivationPermissionChangeGuard,
) -> OpenApiConnectorManagementService:
    current_catalog_importer = OpenApiCurrentCatalogImportService(
        store,
        ids,
        clock,
        permission_change_guard,
        DefaultOpenApiImportPreparer(),
    )
    return OpenApiConnectorManagementService(
        store,
        store,
        current_catalog_importer,
        ids,
        clock,
    )


__all__ = [
    "ActivationPermissionChangeGuard",
    "AllowActivationPermissionChangeGuard",
    "OpenApiConnectorManagementService",
    "compose_openapi_connector_management",
    "OpenApiServerSelectionRequired",
]
