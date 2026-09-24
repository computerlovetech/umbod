import logging
from dataclasses import dataclass

from umbod.core.publishing import ConnectorPublishingStore
from umbod.core.activation import (
    ActivationStatus,
    ActivationStore,
    CapabilityRef,
)
from umbod.core.connectors.downstream_mcp.models import (
    ConnectorHealthy,
    ConnectorUnhealthy,
    CatalogReconciliation,
    DiscoveryFailed,
    DiscoverySucceeded,
)
from umbod.core.connectors.downstream_mcp.stores import (
    ConnectorHealthStore,
    ConnectorIdQuery,
    ReplaceToolCatalog,
    SaveConnectorHealth,
    ToolCatalogFound,
    ToolCatalogStore,
)
from umbod.mcp.downstream_mcp_connectors.capability_notifications import (
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


class DiscoveredCatalogReconciler:
    def __init__(self, dependencies: CatalogReconciliationDependencies) -> None:
        self._dependencies = dependencies

    async def record_failure(self, result: DiscoveryFailed) -> None:
        await self._dependencies.health.save(
            SaveConnectorHealth(
                health=ConnectorUnhealthy(
                    connector_id=result.connector_id,
                    checked_at=result.attempted_at,
                    reason=result.reason,
                )
            )
        )

    async def reconcile(self, result: DiscoverySucceeded) -> None:
        connector_id = result.snapshot.connector_id
        query = ConnectorIdQuery(connector_id=connector_id)
        previous = await self._dependencies.catalogs.get(query)
        previously_enabled = await self._enabled_names(connector_id, previous)

        async def replace_catalog() -> CatalogReconciliation:
            return await self._dependencies.catalogs.replace(
                ReplaceToolCatalog(snapshot=result.snapshot)
            )

        reconciliation = await self._dependencies.native_monitor.apply_and_notify(replace_catalog)
        await self._persist_success(result)
        changed_names = {
            identity.downstream_name for identity in reconciliation.changed + reconciliation.removed
        }
        await self._notify_tool_changes(connector_id, changed_names, previously_enabled)
        logger.info(
            "Downstream MCP discovery reconciled",
            extra={
                "connector_id": connector_id,
                "added_count": len(reconciliation.added),
                "changed_count": len(reconciliation.changed),
                "removed_count": len(reconciliation.removed),
            },
        )

    async def _persist_success(self, result: DiscoverySucceeded) -> None:
        await self._dependencies.activations.reconcile(
            "downstream_mcp",
            result.snapshot.connector_id,
            "tool",
            tuple(tool.identity.downstream_name for tool in result.snapshot.tools),
        )
        await self._dependencies.activations.reconcile(
            "downstream_mcp",
            result.snapshot.connector_id,
            "prompt",
            tuple(prompt.name for prompt in result.snapshot.prompts),
        )
        await self._dependencies.activations.reconcile(
            "downstream_mcp",
            result.snapshot.connector_id,
            "resource",
            tuple(resource.uri for resource in result.snapshot.resources),
        )
        await self._dependencies.activations.reconcile(
            "downstream_mcp",
            result.snapshot.connector_id,
            "resource_template",
            tuple(template.uri_template for template in result.snapshot.resource_templates),
        )
        await self._dependencies.health.save(
            SaveConnectorHealth(
                health=ConnectorHealthy(
                    connector_id=result.snapshot.connector_id,
                    checked_at=result.snapshot.discovered_at,
                )
            )
        )

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
