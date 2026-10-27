from datetime import UTC, datetime

from umbod.core.capabilities.tools.names import PublicToolIdentitySource
from umbod.core.connectors.downstream_mcp.models import (
    ConnectorHealthy,
    ConnectorUnhealthy,
    DiscoveryResult,
    DiscoverySucceeded,
    ToolCatalogSnapshot,
    uses_personal_oauth,
)
from umbod.core.connectors.downstream_mcp.management.queries import DownstreamConnectorQueries
from umbod.core.connectors.downstream_mcp.management.unit_of_work import (
    ApplyDiscoveredCatalog,
    DeleteCatalog,
    DownstreamConnectorUnitOfWork,
    InvalidateDownstreamConnectorAggregate,
)
from umbod.core.connectors.downstream_mcp.probe import (
    DiscoverDownstreamTools,
    DownstreamDiscovery,
)


class DownstreamConnectorCatalogLifecycle:
    def __init__(
        self,
        discovery: DownstreamDiscovery,
        unit_of_work: DownstreamConnectorUnitOfWork,
        queries: DownstreamConnectorQueries,
        identity_source: PublicToolIdentitySource,
    ) -> None:
        self._discovery = discovery
        self._unit_of_work = unit_of_work
        self._queries = queries
        self._identity_source = identity_source

    async def refresh(self, connector_id: str) -> DiscoveryResult:
        admission = await self._unit_of_work.admit_discovery(connector_id)
        definition = admission.definition
        if uses_personal_oauth(definition):
            raise ValueError("Personal OAuth cannot use shared connector discovery")
        result = await self._discovery.discover(
            DiscoverDownstreamTools(definition=definition, credential=admission.credential)
        )
        catalog, health, operation_names = self._discovery_mutations(connector_id, result)
        await self._unit_of_work.apply_discovery(
            ApplyDiscoveredCatalog(
                admission=admission,
                native_identities=await self._identity_source.identities(),
                connector_id=connector_id,
                catalog=catalog,
                health=health,
                operation_names=operation_names,
            )
        )
        return result

    async def invalidate(self, connector_id: str) -> None:
        await self._queries.get(connector_id)
        await self._unit_of_work.invalidate(
            InvalidateDownstreamConnectorAggregate(
                connector_id=connector_id,
                health=ConnectorUnhealthy(
                    connector_id=connector_id,
                    checked_at=datetime.now(UTC),
                    reason="Rediscovery required after authorization change",
                ),
            )
        )

    @staticmethod
    def _discovery_mutations(
        connector_id: str, result: DiscoveryResult
    ) -> tuple[
        ToolCatalogSnapshot | DeleteCatalog, ConnectorHealthy | ConnectorUnhealthy, tuple[str, ...]
    ]:
        if isinstance(result, DiscoverySucceeded):
            names = tuple(tool.identity.downstream_name for tool in result.snapshot.tools)
            return (
                result.snapshot,
                ConnectorHealthy(
                    connector_id=connector_id, checked_at=result.snapshot.discovered_at
                ),
                names,
            )
        return (
            DeleteCatalog(),
            ConnectorUnhealthy(
                connector_id=connector_id, checked_at=result.attempted_at, reason=result.reason
            ),
            (),
        )
