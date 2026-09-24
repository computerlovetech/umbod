from umbod.core.activation import (
    ActivationPort,
    ActivationResult,
    ActivationStore,
    CapabilityRef,
)
from umbod.core.activation.events import connector_capability_activation_changed_event
from umbod.core.invocation import ConnectorKind
from umbod.core.connectors.downstream_mcp.management.queries import DownstreamConnectorQueries
from messaging.ports import EventStream


class DownstreamActivationEventPublicationPolicy:
    def __init__(self, queries: DownstreamConnectorQueries) -> None:
        self._queries = queries

    async def should_publish(self, connector_kind: ConnectorKind, connector_id: str) -> bool:
        return await self._queries.is_published(connector_id)


class DownstreamConnectorActivation:
    def __init__(
        self,
        activation_store: ActivationStore,
        activation: ActivationPort,
        events: EventStream,
        queries: DownstreamConnectorQueries,
    ) -> None:
        self._activation_store = activation_store
        self._activation = activation
        self._events = events
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
        before = await self._activation_store.get_status(ref)
        result = await self._activation.enable(ref) if enabled else await self._activation.disable(ref)
        after = await self._activation_store.get_status(ref)
        if (
            result.state is not None
            and before != after
            and await self._queries.is_published(connector_id)
        ):
            await self._events.append(
                connector_capability_activation_changed_event(
                    "downstream_mcp",
                    connector_id,
                    capability_kind,  # type: ignore[arg-type]
                    capability_key,
                )
            )
        return result
