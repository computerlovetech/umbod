from collections.abc import AsyncIterator

import pytest
import pytest_asyncio

from tests.persistence_runtime import prepared_inmemory_runtime
from umbod.core.activation import (
    ActivationStatus,
    ActivationStore,
    CapabilityRef,
    create_capability_activation_store,
)

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def store() -> AsyncIterator[ActivationStore]:
    runtime = await prepared_inmemory_runtime()
    try:
        yield await create_capability_activation_store(runtime.database)
    finally:
        await runtime.shutdown()


async def test_reconciliation_preserves_current_rows_removes_absent_rows_and_does_not_insert_new_rows(store: ActivationStore) -> None:
    stable = CapabilityRef(connector_kind="openapi", connector_id='inventory', capability_kind="tool", capability_key='stable')
    removed = CapabilityRef(connector_kind="openapi", connector_id='inventory', capability_kind="tool", capability_key='removed')
    introduced = CapabilityRef(connector_kind="openapi", connector_id='inventory', capability_kind="tool", capability_key='introduced')
    other_connector = CapabilityRef(connector_kind="openapi", connector_id='other', capability_kind="tool", capability_key='removed')
    await store.set_status(stable, ActivationStatus.ENABLED)
    await store.set_status(removed, ActivationStatus.ENABLED)
    await store.set_status(other_connector, ActivationStatus.ENABLED)
    await store.reconcile("openapi", 'inventory', "tool", ('stable', 'introduced'))
    assert await store.get_status(stable) == ActivationStatus.ENABLED
    assert await store.get_status(removed) == ActivationStatus.DISABLED
    assert await store.get_status(introduced) == ActivationStatus.DISABLED
    assert await store.get_status(other_connector) == ActivationStatus.ENABLED

async def test_removed_then_reintroduced_operation_defaults_disabled(store: ActivationStore) -> None:
    operation = CapabilityRef(connector_kind="openapi", connector_id='inventory', capability_kind="tool", capability_key='readItems')
    await store.set_status(operation, ActivationStatus.ENABLED)
    await store.reconcile("openapi", 'inventory', "tool", ())
    await store.reconcile("openapi", 'inventory', "tool", ('readItems',))
    assert await store.get_status(operation) == ActivationStatus.DISABLED
