import pytest

from umbod.core.activation import ActivationStatus, CapabilityRef, create_capability_activation_store
from tests.persistence_runtime import prepared_inmemory_runtime


@pytest.mark.asyncio
async def test_create_capability_activation_store_uses_supplied_database() -> None:
    runtime = await prepared_inmemory_runtime()
    try:
        store = await create_capability_activation_store(runtime.database)
        recreated = await create_capability_activation_store(runtime.database)
        tool = CapabilityRef(connector_kind="native", connector_id="github", capability_kind="tool", capability_key="search_issues")
        await store.set_status(tool, ActivationStatus.ENABLED)
        assert await store.get_status(tool) == ActivationStatus.ENABLED
        assert await recreated.get_status(tool) == ActivationStatus.ENABLED
    finally:
        await runtime.shutdown()
