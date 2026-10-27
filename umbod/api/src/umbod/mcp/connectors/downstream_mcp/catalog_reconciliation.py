import logging

from umbod.core.connectors.downstream_mcp.errors import ObsoleteDownstreamCatalogError
from dataclasses import dataclass

from umbod.core.capabilities.tools.names import PublicToolIdentitySource
from umbod.core.connectors.downstream_mcp.management import ApplyDiscoveredCatalog, DownstreamConnectorUnitOfWork, KeepCatalog

from umbod.core.publishing import ConnectorPublishingStore
from umbod.core.activation import (
    ActivationStatus,
    ActivationStore,
    CapabilityRef,
)
from umbod.core.connectors.downstream_mcp.models import (
    ConnectorHealthy,
    ConnectorUnhealthy,
    DefinitionDiscoverySucceeded,
    DefinitionDiscoveryFailed,
    DiscoveryFailed,
    DiscoverySucceeded,
)
from umbod.core.connectors.downstream_mcp.stores import (
    ConnectorHealthStore,
    ConnectorIdQuery,
    ToolCatalogFound,
    ToolCatalogStore,
)
from umbod.mcp.connectors.downstream_mcp.capability_notifications import (
    NativeCapabilityChangeMonitor,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CatalogReconciliationDependencies:
    catalogs: ToolCatalogStore
    health: ConnectorHealthStore
    activations: ActivationStore
    publishing: ConnectorPublishingStore
    native_monitor: NativeCapabilityChangeMonitor
    unit_of_work: DownstreamConnectorUnitOfWork
    identity_source: PublicToolIdentitySource


class DiscoveredCatalogReconciler:
    def __init__(self, dependencies: CatalogReconciliationDependencies) -> None:
        self._dependencies = dependencies

    async def record_failure(self, result: DiscoveryFailed) -> None:
        if not isinstance(result, DefinitionDiscoveryFailed):
            raise ValueError("Discovery must retain its admission")
        try:
            await self._dependencies.unit_of_work.apply_discovery(ApplyDiscoveredCatalog(
                admission=result.admission,
                native_identities=await self._dependencies.identity_source.identities(),
                connector_id=result.connector_id, catalog=KeepCatalog(), operation_names=(),
                health=ConnectorUnhealthy(
                    connector_id=result.connector_id, checked_at=result.attempted_at, reason=result.reason,
                ),
            ))
        except ObsoleteDownstreamCatalogError:
            return

    async def reconcile(self, result: DiscoverySucceeded) -> None:
        connector_id = result.snapshot.connector_id
        query = ConnectorIdQuery(connector_id=connector_id)
        previous = await self._dependencies.catalogs.get(query)
        previously_enabled = await self._enabled_names(connector_id, previous)

        if not isinstance(result, DefinitionDiscoverySucceeded):
            raise ValueError("Discovery must retain its probed definition")

        async def replace_catalog() -> None:
            await self._dependencies.unit_of_work.apply_discovery(
                ApplyDiscoveredCatalog(
                    admission=result.admission,
                    native_identities=await self._dependencies.identity_source.identities(),
                    connector_id=connector_id,
                    catalog=result.snapshot,
                    health=ConnectorHealthy(connector_id=connector_id, checked_at=result.snapshot.discovered_at),
                    operation_names=tuple(tool.identity.downstream_name for tool in result.snapshot.tools),
                )
            )

        try:
            await self._dependencies.native_monitor.apply_and_notify(replace_catalog)
        except ObsoleteDownstreamCatalogError:
            return
        await self._notify_tool_changes(connector_id, previously_enabled, previously_enabled)
        logger.info("Downstream MCP discovery reconciled", extra={"connector_id": connector_id})

    async def _notify_tool_changes(
        self,
        connector_id: str,
        changed_names: set[str],
        previously_enabled: set[str],
    ) -> None:
        if (
            await self._dependencies.publishing.is_published(connector_id)
            and changed_names & previously_enabled
        ):
            self._dependencies.native_monitor.notify_tool_list_changed()

    async def _enabled_names(self, connector_id: str, catalog: object) -> set[str]:
        if not isinstance(catalog, ToolCatalogFound):
            return set()
        enabled: set[str] = set()
        for tool in catalog.snapshot.tools:
            status = await self._dependencies.activations.get_status(
                CapabilityRef(
                    connector_kind="downstream_mcp",
                    connector_id=connector_id,
                    capability_kind="tool",
                    capability_key=tool.identity.downstream_name,
                )
            )
            if status == ActivationStatus.ENABLED:
                enabled.add(tool.identity.downstream_name)
        return enabled
