from collections.abc import AsyncIterator

import pytest
import pytest_asyncio

from umbod.core.activation import (
    ActivationStatus,
    ActivationStore,
    CapabilityRef,
    create_capability_activation_store,
)
from tests.persistence_runtime import prepared_inmemory_runtime
from umbod.core.persistence import Database


def _ref(
    connector_id: str,
    capability_key: str,
    *,
    connector_kind: str = "native",
    capability_kind: str = "tool",
) -> CapabilityRef:
    return CapabilityRef(
        connector_kind=connector_kind,  # type: ignore[arg-type]
        connector_id=connector_id,
        capability_kind=capability_kind,  # type: ignore[arg-type]
        capability_key=capability_key,
    )


@pytest_asyncio.fixture
async def database() -> AsyncIterator[Database]:
    runtime = await prepared_inmemory_runtime()
    try:
        yield runtime.database
    finally:
        await runtime.shutdown()


@pytest_asyncio.fixture
async def store(database: Database) -> ActivationStore:
    return await create_capability_activation_store(database)


@pytest.mark.asyncio
async def test_missing_capability_is_disabled_by_default(store: ActivationStore) -> None:
    assert await store.get_status(_ref("github", "search_issues")) == ActivationStatus.DISABLED


@pytest.mark.asyncio
async def test_set_status_roundtrips_enabled_and_disabled(store: ActivationStore) -> None:
    ref = _ref("github", "search_issues")
    await store.set_status(ref, ActivationStatus.ENABLED)
    assert await store.get_status(ref) == ActivationStatus.ENABLED
    await store.set_status(ref, ActivationStatus.DISABLED)
    assert await store.get_status(ref) == ActivationStatus.DISABLED


@pytest.mark.asyncio
async def test_statuses_are_scoped_by_kind_connector_and_key(store: ActivationStore) -> None:
    enabled = _ref("github", "search_issues")
    other_connector = _ref("gitlab", "search_issues")
    other_key = _ref("github", "create_issue")
    other_capability = _ref("github", "search_issues", capability_kind="prompt")
    other_kind = _ref("github", "search_issues", connector_kind="downstream_mcp")
    await store.set_status(enabled, ActivationStatus.ENABLED)
    assert await store.get_status(enabled) == ActivationStatus.ENABLED
    assert await store.get_status(other_connector) == ActivationStatus.DISABLED
    assert await store.get_status(other_key) == ActivationStatus.DISABLED
    assert await store.get_status(other_capability) == ActivationStatus.DISABLED
    assert await store.get_status(other_kind) == ActivationStatus.DISABLED


@pytest.mark.asyncio
async def test_reconcile_removes_stale_keys_for_kind(store: ActivationStore) -> None:
    keep = _ref("github", "search_issues")
    drop = _ref("github", "create_issue")
    prompt = _ref("github", "search_issues", capability_kind="prompt")
    await store.set_status(keep, ActivationStatus.ENABLED)
    await store.set_status(drop, ActivationStatus.ENABLED)
    await store.set_status(prompt, ActivationStatus.ENABLED)
    await store.reconcile("native", "github", "tool", ("search_issues",))
    assert await store.get_status(keep) == ActivationStatus.ENABLED
    assert await store.get_status(drop) == ActivationStatus.DISABLED
    assert await store.get_status(prompt) == ActivationStatus.ENABLED


@pytest.mark.asyncio
async def test_store_instances_share_activation_state(database: Database) -> None:
    writer = await create_capability_activation_store(database)
    reader = await create_capability_activation_store(database)
    ref = _ref("github", "search_issues")
    await writer.set_status(ref, ActivationStatus.ENABLED)
    assert await reader.get_status(ref) == ActivationStatus.ENABLED
    await writer.set_status(ref, ActivationStatus.DISABLED)
    assert await reader.get_status(ref) == ActivationStatus.DISABLED
