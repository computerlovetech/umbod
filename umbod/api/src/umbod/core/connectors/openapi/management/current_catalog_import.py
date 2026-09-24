from typing import Protocol

from umbod.core.connectors.openapi.importing.preparation import (
    OpenApiImportPreparer,
    OpenApiServerSelectionRequired,
)
from umbod.core.connectors.openapi.management.models import (
    ImportOpenApiCatalog,
    OpenApiConnectorCatalog,
    ReplaceCurrentOpenApiCatalog,
)
from umbod.core.connectors.openapi.stores import (
    AtomicCurrentOpenApiCatalogWriter,
    CurrentOpenApiCatalogReader,
    OpenApiConnectorReader,
)


class CurrentOpenApiCatalogStore(
    OpenApiConnectorReader,
    CurrentOpenApiCatalogReader,
    AtomicCurrentOpenApiCatalogWriter,
    Protocol,
): ...


class OpenApiIdGenerator(Protocol):
    def new_id(self) -> str: ...


class OpenApiClock(Protocol):
    def now(self) -> str: ...


class ActivationPermissionChangeGuard(Protocol):
    async def validate_change(
        self,
        connector_id: str,
        previous_operation_ids: frozenset[str],
        next_operation_ids: frozenset[str],
    ) -> None: ...


class AllowActivationPermissionChangeGuard:
    async def validate_change(
        self,
        connector_id: str,
        previous_operation_ids: frozenset[str],
        next_operation_ids: frozenset[str],
    ) -> None:
        return None


class OpenApiCurrentCatalogImportService:
    def __init__(
        self,
        store: CurrentOpenApiCatalogStore,
        ids: OpenApiIdGenerator,
        clock: OpenApiClock,
        permission_change_guard: ActivationPermissionChangeGuard,
        import_preparer: OpenApiImportPreparer,
    ) -> None:
        self._store = store
        self._ids = ids
        self._clock = clock
        self._permission_change_guard = permission_change_guard
        self._import_preparer = import_preparer

    async def import_current_catalog(
        self, request: ImportOpenApiCatalog
    ) -> OpenApiConnectorCatalog:
        connector = await self._store.get_connector(request.connector_id)
        prepared = self._import_preparer.prepare(request)
        await self._validate_operation_change(connector.connector_id, prepared.operation_ids)
        timestamp = self._clock.now()
        catalog_id = self._ids.new_id()
        current_connector = connector.model_copy(update={"updated_at": timestamp})
        catalog = OpenApiConnectorCatalog(
            connector_id=connector.connector_id,
            catalog_id=catalog_id,
            source_document=prepared.source_document,
            candidate=prepared.candidate,
            approved_hosts=prepared.approved_hosts,
            selected_server_url=prepared.selected_server_url,
            operation_ids=prepared.operation_ids,
            imported_at=timestamp,
        )
        return await self._store.replace_current_catalog(
            ReplaceCurrentOpenApiCatalog(connector=current_connector, catalog=catalog)
        )

    async def _validate_operation_change(
        self, connector_id: str, next_operation_ids: tuple[str, ...]
    ) -> None:
        previous = await self._store.read_current_catalog(connector_id)
        previous_operation_ids = (
            frozenset() if previous is None else frozenset(previous.operation_ids)
        )
        await self._permission_change_guard.validate_change(
            connector_id,
            previous_operation_ids,
            frozenset(next_operation_ids),
        )


__all__ = [
    "ActivationPermissionChangeGuard",
    "AllowActivationPermissionChangeGuard",
    "CurrentOpenApiCatalogStore",
    "OpenApiClock",
    "OpenApiCurrentCatalogImportService",
    "OpenApiIdGenerator",
    "OpenApiServerSelectionRequired",
]
