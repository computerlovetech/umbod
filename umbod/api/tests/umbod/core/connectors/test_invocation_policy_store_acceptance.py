from tests.persistence_runtime import create_inmemory_runtime
import pytest
from umbod.core.invocation import ConnectorInvocationPolicyKey, ConnectorInvocationPolicyRevisionConflict, ConnectorInvocationPolicyUpdate, ConnectorKind
from umbod.core.invocation import CONNECTOR_INVOCATION_POLICY_TABLE, DatabaseConnectorInvocationPolicyStore

@pytest.mark.asyncio
@pytest.mark.parametrize('connector_kind', ['native', 'openapi', 'downstream_mcp'])
async def test_compare_and_set_contract_is_atomic_for_every_connector_kind(connector_kind: ConnectorKind) -> None:
    database = create_inmemory_runtime().database
    await database.ensure_schema((CONNECTOR_INVOCATION_POLICY_TABLE,))
    store = DatabaseConnectorInvocationPolicyStore(database)
    first = ConnectorInvocationPolicyKey(connector_kind, 'connector', 'first')
    second = ConnectorInvocationPolicyKey(connector_kind, 'connector', 'second')
    records = await store.compare_and_set_batch((ConnectorInvocationPolicyUpdate(first, 'ask', 0), ConnectorInvocationPolicyUpdate(second, 'direct', 0)))
    assert tuple((record.revision for record in records)) == (1, 0)
    assert await store.get(second) is None
    unchanged = await store.compare_and_set_batch((ConnectorInvocationPolicyUpdate(first, 'ask', 1),))
    assert unchanged[0].revision == 1
    with pytest.raises(ConnectorInvocationPolicyRevisionConflict) as raised:
        await store.compare_and_set_batch((ConnectorInvocationPolicyUpdate(first, 'direct', 0), ConnectorInvocationPolicyUpdate(second, 'ask', 0)))
    assert tuple((conflict.key for conflict in raised.value.conflicts)) == (first,)
    persisted = await store.list((first, second))
    assert tuple((record.mode if record is not None else None for record in persisted)) == ('ask', None)

@pytest.mark.asyncio
@pytest.mark.parametrize('connector_kind', ['native', 'openapi', 'downstream_mcp'])
async def test_connector_deletion_removes_only_matching_policy_rows(connector_kind: ConnectorKind) -> None:
    database = create_inmemory_runtime().database
    await database.ensure_schema((CONNECTOR_INVOCATION_POLICY_TABLE,))
    store = DatabaseConnectorInvocationPolicyStore(database)
    deleted = ConnectorInvocationPolicyKey(connector_kind, 'deleted', 'tool')
    retained = ConnectorInvocationPolicyKey(connector_kind, 'retained', 'tool')
    await store.compare_and_set_batch((ConnectorInvocationPolicyUpdate(deleted, 'ask', 0), ConnectorInvocationPolicyUpdate(retained, 'ask', 0)))
    await store.delete_connector(connector_kind, 'deleted')
    assert await store.list((deleted, retained)) == (None, await store.get(retained))
