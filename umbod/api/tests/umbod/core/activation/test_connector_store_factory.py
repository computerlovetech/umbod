from umbod.core.activation import CapabilityRef, create_capability_activation_store
from tests.persistence_runtime import prepared_inmemory_runtime, prepared_sqlite_runtime
from pathlib import Path
import pytest
from umbod.core.activation import ActivationStatus

@pytest.mark.asyncio
async def test_create_capability_activation_store_uses_in_memory_store_for_inmemory(tmp_path: Path) -> None:
    database = (await prepared_inmemory_runtime()).database
    store = await create_capability_activation_store(database)
    tool = CapabilityRef(connector_kind="native", connector_id='github', capability_kind="tool", capability_key='search_issues')
    await store.set_status(tool, ActivationStatus.ENABLED)
    assert await store.get_status(tool) == ActivationStatus.ENABLED

@pytest.mark.asyncio
async def test_create_capability_activation_store_uses_sqlite_store_for_sqlite(tmp_path: Path) -> None:
    database = (await prepared_sqlite_runtime(tmp_path / 'connectors.sqlite')).database
    store = await create_capability_activation_store(database)
    tool = CapabilityRef(connector_kind="native", connector_id='github', capability_kind="tool", capability_key='search_issues')
    await store.set_status(tool, ActivationStatus.ENABLED)
    assert await store.get_status(tool) == ActivationStatus.ENABLED
