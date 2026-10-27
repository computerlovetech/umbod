from umbod.core.activation import (
    ActivationPort,
    ActivationResult,
    CapabilityRef,
)
from umbod.core.invocation import ConnectorKind
from umbod.core.connectors.downstream_mcp.management.queries import DownstreamConnectorQueries


class DownstreamActivationEventPublicationPolicy:
    def __init__(self, queries: DownstreamConnectorQueries) -> None:
        self._queries = queries

    async def should_publish(self, connector_kind: ConnectorKind, connector_id: str) -> bool:
        return await self._queries.is_published(connector_id)


class DownstreamConnectorActivation:
    def __init__(
        self,
        activation: ActivationPort,
        queries: DownstreamConnectorQueries,
    ) -> None:
        self._activation = activation
        self._queries = queries

    async def set_activation(
        self,
        connector_id: str,
        capability_key: str,
        enabled: bool,
        *,
        capability_kind: str = "tool",
    ) -> ActivationResult:
        await self._queries.get(connector_id)
        ref = CapabilityRef(
            connector_kind="downstream_mcp",
            connector_id=connector_id,
            capability_kind=capability_kind,  # type: ignore[arg-type]
            capability_key=capability_key,
        )
        return await self._activation.enable(ref) if enabled else await self._activation.disable(ref)
