from umbod.core.invocation.tools.database_configuration_mutation import DatabaseConnectorToolConfigurationMutationAdapter
from tests.persistence_runtime import create_inmemory_runtime
from collections.abc import Awaitable, Callable
import pytest
from umbod.core.invocation import ConnectorInvocationPolicyRevisionConflict
from umbod.core.invocation import CONNECTOR_INVOCATION_POLICY_TABLE
from umbod.core.invocation.tools.configuration_mutation import ConnectorToolActivationChange, ConnectorToolConfigurationMutation, ConnectorToolConfigurationMutationPort, ConnectorToolInvocationPolicyChange, InMemoryConnectorToolConfigurationMutationAdapter
from umbod.core.activation import ActivationStatus
from umbod.core.activation import CAPABILITY_ACTIVATION_STATE_TABLE

async def _in_memory_port() -> ConnectorToolConfigurationMutationPort:
    return InMemoryConnectorToolConfigurationMutationAdapter()

async def _database_port() -> ConnectorToolConfigurationMutationPort:
    database = create_inmemory_runtime().database
    await database.ensure_schema((CONNECTOR_INVOCATION_POLICY_TABLE, CAPABILITY_ACTIVATION_STATE_TABLE))
    return DatabaseConnectorToolConfigurationMutationAdapter(database)

@pytest.mark.asyncio
@pytest.mark.parametrize('factory', [_in_memory_port, _database_port], ids=['memory', 'database'])
async def test_mutation_port_applies_combined_and_noop_changes(factory: Callable[[], Awaitable[ConnectorToolConfigurationMutationPort]]) -> None:
    port = await factory()
    mutation = ConnectorToolConfigurationMutation(connector_kind='native', connector_id='connector', activation_changes=(ConnectorToolActivationChange(operation_name='tool', status=ActivationStatus.ENABLED),), policy_changes=(ConnectorToolInvocationPolicyChange(operation_name='tool', mode='ask', expected_revision=0),))
    changed = await port.apply(mutation)
    unchanged = await port.apply(mutation.model_copy(update={'policy_changes': (ConnectorToolInvocationPolicyChange(operation_name='tool', mode='ask', expected_revision=1),)}))
    assert changed.changed_activations == mutation.activation_changes
    assert changed.policies[0].revision == 1
    assert changed.policies[0].changed is True
    assert unchanged.changed_activations == ()
    assert unchanged.policies[0].revision == 1
    assert unchanged.policies[0].changed is False

@pytest.mark.asyncio
@pytest.mark.parametrize('factory', [_in_memory_port, _database_port], ids=['memory', 'database'])
async def test_mutation_port_discovers_all_conflicts_before_activation_writes(factory: Callable[[], Awaitable[ConnectorToolConfigurationMutationPort]]) -> None:
    port = await factory()
    await port.apply(ConnectorToolConfigurationMutation(connector_kind='openapi', connector_id='connector', policy_changes=(ConnectorToolInvocationPolicyChange(operation_name='first', mode='ask', expected_revision=0), ConnectorToolInvocationPolicyChange(operation_name='second', mode='ask', expected_revision=0))))
    with pytest.raises(ConnectorInvocationPolicyRevisionConflict) as raised:
        await port.apply(ConnectorToolConfigurationMutation(connector_kind='openapi', connector_id='connector', activation_changes=(ConnectorToolActivationChange(operation_name='activation', status=ActivationStatus.ENABLED),), policy_changes=(ConnectorToolInvocationPolicyChange(operation_name='first', mode='direct', expected_revision=0), ConnectorToolInvocationPolicyChange(operation_name='second', mode='direct', expected_revision=0))))
    assert tuple((conflict.key.operation_name for conflict in raised.value.conflicts)) == ('first', 'second')
    result = await port.apply(ConnectorToolConfigurationMutation(connector_kind='openapi', connector_id='connector', activation_changes=(ConnectorToolActivationChange(operation_name='activation', status=ActivationStatus.ENABLED),)))
    assert result.changed_activations[0].operation_name == 'activation'

@pytest.mark.asyncio
@pytest.mark.parametrize('factory', [_in_memory_port, _database_port], ids=['memory', 'database'])
async def test_mutation_result_preserves_submitted_multi_tool_order(factory: Callable[[], Awaitable[ConnectorToolConfigurationMutationPort]]) -> None:
    port = await factory()
    mutation = ConnectorToolConfigurationMutation(connector_kind='downstream_mcp', connector_id='connector', operation_names=('second', 'first'), activation_changes=(ConnectorToolActivationChange(operation_name='second', status=ActivationStatus.ENABLED),), policy_changes=(ConnectorToolInvocationPolicyChange(operation_name='first', mode='ask', expected_revision=0),))
    result = await port.apply(mutation)
    assert tuple((item.operation_name for item in result.snapshots)) == ('second', 'first')
    assert tuple((item.activation_status for item in result.snapshots)) == (ActivationStatus.ENABLED, ActivationStatus.DISABLED)
    assert tuple((item.invocation_mode for item in result.snapshots)) == ('direct', 'ask')
    assert tuple((item.policy_revision for item in result.snapshots)) == (0, 1)
