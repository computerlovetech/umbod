from umbod.core.activation import (
    ActivationStatus,
    ActivationStore,
    CapabilityRef,
    create_capability_activation_store,
)
from tests.persistence_runtime import prepared_inmemory_runtime, prepared_sqlite_runtime
from pathlib import Path
from typing import Awaitable, Callable
import pytest
pytestmark = pytest.mark.asyncio
ActivationStoreFactory = Callable[[Path], Awaitable[ActivationStore]]

async def _in_memory_store(_path: Path) -> ActivationStore:
    database = (await prepared_inmemory_runtime()).database
    return await create_capability_activation_store(database)

async def _sqlite_store(path: Path) -> ActivationStore:
    database = (await prepared_sqlite_runtime(path)).database
    return await create_capability_activation_store(database)

@pytest.mark.parametrize('factory', [_in_memory_store, _sqlite_store], ids=['in_memory', 'sqlite'])
async def test_reconciliation_preserves_current_rows_removes_absent_rows_and_does_not_insert_new_rows(tmp_path: Path, factory: ActivationStoreFactory) -> None:
    store = await factory(tmp_path / 'activation.sqlite')
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

@pytest.mark.parametrize('factory', [_in_memory_store, _sqlite_store], ids=['in_memory', 'sqlite'])
async def test_removed_then_reintroduced_operation_defaults_disabled(tmp_path: Path, factory: ActivationStoreFactory) -> None:
    store = await factory(tmp_path / 'activation.sqlite')
    operation = CapabilityRef(connector_kind="openapi", connector_id='inventory', capability_kind="tool", capability_key='readItems')
    await store.set_status(operation, ActivationStatus.ENABLED)
    await store.reconcile("openapi", 'inventory', "tool", ())
    await store.reconcile("openapi", 'inventory', "tool", ('readItems',))
    assert await store.get_status(operation) == ActivationStatus.DISABLED
