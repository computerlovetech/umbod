from collections.abc import Sequence

import pytest
from messaging.models import MessagingEvent, MessagingEventType, StreamEvent

from umbod.core.invocation import (
    ConnectorInvocationPolicyRevisionConflict,
    ConnectorKind,
)
from umbod.core.invocation.tools.configuration import ActivationEventPublicationPolicy, AlwaysPublishActivationEvents, NoConnectorToolConfigurationEventStream, SetConnectorToolActivation, SetConnectorToolConfiguration, SetConnectorToolConfigurationCommand, SetConnectorToolInvocationPolicy, SuppressActivationEvents
from umbod.core.invocation.tools.configuration_mutation import ConnectorToolConfigurationMutation, ConnectorToolConfigurationMutationResult, InMemoryConnectorToolConfigurationMutationAdapter


class RecordingPublicationPolicy:
    def __init__(self, mutation_applied: list[bool], published: bool) -> None:
        self._mutation_applied = mutation_applied
        self._published = published
        self.evaluated_after_mutation = False

    async def should_publish(self, connector_kind: ConnectorKind, connector_id: str) -> bool:
        self.evaluated_after_mutation = self._mutation_applied == [True]
        return self._published


class RecordingMutationPort:
    def __init__(self, mutation_applied: list[bool]) -> None:
        self._adapter = InMemoryConnectorToolConfigurationMutationAdapter()
        self._mutation_applied = mutation_applied

    async def apply(
        self, mutation: ConnectorToolConfigurationMutation
    ) -> ConnectorToolConfigurationMutationResult:
        result = await self._adapter.apply(mutation)
        self._mutation_applied.append(True)
        return result


class RecordingEventStream:
    def __init__(self) -> None:
        self.events: list[MessagingEvent] = []

    async def append(self, event: MessagingEvent) -> StreamEvent:
        self.events.append(event)
        return StreamEvent(sequence=len(self.events), event=event)

    async def list_after(self, sequence: int, limit: int) -> list[StreamEvent]:
        return []

    async def list_after_types(
        self,
        sequence: int,
        limit: int,
        event_types: Sequence[MessagingEventType],
    ) -> list[StreamEvent]:
        return []


def _command(
    connector_kind: ConnectorKind,
    expected_policy_revision: int,
) -> SetConnectorToolConfigurationCommand:
    return SetConnectorToolConfigurationCommand.model_validate(
        {
            "connector_kind": connector_kind,
            "connector_id": "connector",
            "items": [
                {
                    "operation_name": "tool",
                    "activation_status": "enabled",
                    "invocation_mode": "ask",
                    "expected_policy_revision": expected_policy_revision,
                }
            ],
        }
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("policy", "expected"),
    [(AlwaysPublishActivationEvents(), True), (SuppressActivationEvents(), False)],
)
async def test_in_memory_publication_policies_implement_protocol(
    policy: ActivationEventPublicationPolicy, expected: bool
) -> None:
    assert await policy.should_publish("native", "connector") is expected


@pytest.mark.asyncio
async def test_service_evaluates_activation_publication_after_mutation() -> None:
    mutation_applied: list[bool] = []
    policy = RecordingPublicationPolicy(mutation_applied, True)
    service = SetConnectorToolConfiguration(
        RecordingMutationPort(mutation_applied), RecordingEventStream(), policy
    )

    await service.execute(_command("downstream_mcp", 0))

    assert policy.evaluated_after_mutation


@pytest.mark.asyncio
@pytest.mark.parametrize("connector_kind", ["native", "openapi"])
async def test_service_emits_activation_and_policy_events_for_standard_connectors(
    connector_kind: ConnectorKind,
) -> None:
    stream = RecordingEventStream()
    service = SetConnectorToolConfiguration(
        InMemoryConnectorToolConfigurationMutationAdapter(), stream, AlwaysPublishActivationEvents()
    )

    result = await service.execute(_command(connector_kind, 0))

    assert result.snapshots[0].operation_name == "tool"
    assert [event.event_type for event in stream.events] == [
        "connector.capability_activation.changed",
        "connector.invocation_policy.changed",
    ]
    assert stream.events[1].metadata["connector_kind"] == connector_kind


@pytest.mark.asyncio
async def test_service_suppresses_unpublished_downstream_activation_event_only() -> None:
    stream = RecordingEventStream()
    service = SetConnectorToolConfiguration(
        InMemoryConnectorToolConfigurationMutationAdapter(), stream, SuppressActivationEvents()
    )

    await service.execute(_command("downstream_mcp", 0))

    assert [event.event_type for event in stream.events] == ["connector.invocation_policy.changed"]


@pytest.mark.asyncio
async def test_service_applies_changes_without_event_stream() -> None:
    service = SetConnectorToolConfiguration(
        InMemoryConnectorToolConfigurationMutationAdapter(),
        NoConnectorToolConfigurationEventStream(),
        AlwaysPublishActivationEvents(),
    )

    result = await service.execute(_command("native", 0))

    assert result.snapshots[0].activation_status.value == "enabled"
    assert result.snapshots[0].invocation_mode == "ask"


@pytest.mark.asyncio
async def test_service_propagates_conflict_without_events_or_activation_change() -> None:
    adapter = InMemoryConnectorToolConfigurationMutationAdapter()
    stream = RecordingEventStream()
    service = SetConnectorToolConfiguration(adapter, stream, AlwaysPublishActivationEvents())
    await service.execute(
        SetConnectorToolConfigurationCommand(
            connector_kind="openapi",
            connector_id="connector",
            items=(
                SetConnectorToolInvocationPolicy(
                    operation_name="tool", invocation_mode="ask", expected_policy_revision=0
                ),
            ),
        )
    )
    stream.events.clear()

    with pytest.raises(ConnectorInvocationPolicyRevisionConflict):
        await service.execute(_command("openapi", 0))

    assert stream.events == []
    result = await service.execute(
        SetConnectorToolConfigurationCommand(
            connector_kind="openapi",
            connector_id="connector",
            items=(
                SetConnectorToolInvocationPolicy(
                    operation_name="tool", invocation_mode="ask", expected_policy_revision=1
                ),
            ),
        )
    )
    assert result.snapshots[0].activation_status.value == "disabled"


@pytest.mark.asyncio
async def test_service_preserves_first_occurrence_request_order() -> None:
    service = SetConnectorToolConfiguration(
        InMemoryConnectorToolConfigurationMutationAdapter(),
        NoConnectorToolConfigurationEventStream(),
        AlwaysPublishActivationEvents(),
    )
    command = SetConnectorToolConfigurationCommand(
        connector_kind="native",
        connector_id="connector",
        items=(
            SetConnectorToolActivation(operation_name="second", activation_status="enabled"),
            SetConnectorToolInvocationPolicy(
                operation_name="first", invocation_mode="ask", expected_policy_revision=0
            ),
            SetConnectorToolActivation(operation_name="second", activation_status="enabled"),
        ),
    )

    result = await service.execute(command)

    assert tuple(snapshot.operation_name for snapshot in result.snapshots) == ("second", "first")


@pytest.mark.asyncio
async def test_service_emits_events_only_for_changed_values() -> None:
    adapter = InMemoryConnectorToolConfigurationMutationAdapter()
    stream = RecordingEventStream()
    service = SetConnectorToolConfiguration(adapter, stream, AlwaysPublishActivationEvents())
    await service.execute(_command("native", 0))
    stream.events.clear()

    await service.execute(_command("native", 1))

    assert stream.events == []
