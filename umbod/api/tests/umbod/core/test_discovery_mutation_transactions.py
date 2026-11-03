import sqlite3
from pathlib import Path

import pytest

from tests.persistence_runtime import prepared_sqlite_runtime
from umbod.core.activation import ActivationStatus, ActivationStore, CapabilityActivationState, CapabilityRef, create_capability_activation_store
from umbod.core.capabilities.descriptions import ClearCapabilityDescriptionOverride, ConnectorCapabilityDescriptionKey, ConnectorCapabilityDescriptionOverrideStore, SetCapabilityDescriptionOverride
from umbod.core.capabilities.descriptions.factories import ConfiguredConnectorCapabilityDescriptionOverrideStoreFactory
from umbod.core.invocation.tools.configuration_mutation import ConnectorToolActivationChange, ConnectorToolConfigurationMutation, ConnectorToolConfigurationMutationPort, ConnectorToolInvocationPolicyChange
from umbod.core.invocation.tools.database_configuration_mutation import DatabaseConnectorToolConfigurationMutationAdapter
from umbod.core.messaging.stores.event_stream import DatabaseEventStream


@pytest.mark.asyncio
@pytest.mark.parametrize("mutation", (
    "single_activation", "batch_activation", "tool_configuration", "activation_reconcile",
    "description_set", "description_clear", "description_delete",
))
async def test_discovery_event_append_failure_rolls_back_mutation(tmp_path: Path, mutation: str) -> None:
    path = tmp_path / "events.sqlite3"
    runtime = await prepared_sqlite_runtime(path)
    activations: ActivationStore = await create_capability_activation_store(runtime.database)
    descriptions: ConnectorCapabilityDescriptionOverrideStore = await ConfiguredConnectorCapabilityDescriptionOverrideStoreFactory(runtime.database).create()
    tools: ConnectorToolConfigurationMutationPort = DatabaseConnectorToolConfigurationMutationAdapter(runtime.database)
    ref = CapabilityRef(connector_kind="native", connector_id="test", capability_kind="tool", capability_key="echo")
    key = ConnectorCapabilityDescriptionKey(kind="native", connector_id="test")
    if mutation in ("description_clear", "description_delete"):
        await descriptions.set(SetCapabilityDescriptionOverride(key=key, description="Original", expected_revision=0))
    if mutation == "activation_reconcile":
        await activations.set_status(ref, ActivationStatus.ENABLED)
    original_description = await descriptions.get(key)
    original_activation = await activations.get_status(ref)
    events = DatabaseEventStream(runtime.database)
    original_events = await events.list_after(0, 100)
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TRIGGER reject_event BEFORE INSERT ON messaging_events BEGIN SELECT RAISE(ABORT, 'event append failed'); END")
    with pytest.raises(sqlite3.IntegrityError, match="event append failed"):
        if mutation == "single_activation":
            await activations.set_status(ref, ActivationStatus.ENABLED)
        elif mutation == "batch_activation":
            await activations.set_statuses((CapabilityActivationState(ref=ref, activation_status=ActivationStatus.ENABLED),))
        elif mutation == "tool_configuration":
            await tools.apply(ConnectorToolConfigurationMutation(
                connector_kind="native", connector_id="test",
                activation_changes=(ConnectorToolActivationChange(operation_name="echo", status=ActivationStatus.ENABLED),),
                policy_changes=(ConnectorToolInvocationPolicyChange(operation_name="echo", mode="ask", expected_revision=0),),
            ))
        elif mutation == "activation_reconcile":
            await activations.reconcile("native", "test", "tool", ())
        elif mutation == "description_set":
            await descriptions.set(SetCapabilityDescriptionOverride(key=key, description="Changed", expected_revision=0))
        elif mutation == "description_clear":
            await descriptions.clear(ClearCapabilityDescriptionOverride(key=key, expected_revision=1))
        else:
            await descriptions.delete(key)
    assert await descriptions.get(key) == original_description
    assert await activations.get_status(ref) == original_activation
    assert await events.list_after(0, 100) == original_events
    snapshot = await tools.apply(ConnectorToolConfigurationMutation(
        connector_kind="native", connector_id="test", operation_names=("echo",),
    ))
    assert snapshot.snapshots[0].invocation_mode == "direct"
    assert snapshot.snapshots[0].policy_revision == 0
