from collections.abc import Awaitable, Callable
from pathlib import Path

import pytest

from umbod.core.activation import (
    ActivationStatus,
    ActivationStore,
    CapabilityRef,
    create_capability_activation_store,
)
from tests.persistence_runtime import prepared_inmemory_runtime, prepared_sqlite_runtime

ActivationStoreFactory = Callable[[Path], Awaitable[ActivationStore]]


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


async def _in_memory_activation_store(_tmp_path: Path) -> ActivationStore:
    database = (await prepared_inmemory_runtime()).database
    return await create_capability_activation_store(database)


async def _sqlite_activation_store(tmp_path: Path) -> ActivationStore:
    database = (await prepared_sqlite_runtime(tmp_path / "connectors.sqlite")).database
    return await create_capability_activation_store(database)


@pytest.fixture(params=[_in_memory_activation_store, _sqlite_activation_store])
def activation_store_factory(request: pytest.FixtureRequest) -> ActivationStoreFactory:
    return request.param


@pytest.mark.asyncio
async def test_missing_capability_is_disabled_by_default(
    activation_store_factory: ActivationStoreFactory, tmp_path: Path
) -> None:
    store = await activation_store_factory(tmp_path)
    assert await store.get_status(_ref("github", "search_issues")) == ActivationStatus.DISABLED


@pytest.mark.asyncio
async def test_set_status_roundtrips_enabled_and_disabled(
    activation_store_factory: ActivationStoreFactory, tmp_path: Path
) -> None:
    store = await activation_store_factory(tmp_path)
    ref = _ref("github", "search_issues")
    await store.set_status(ref, ActivationStatus.ENABLED)
    assert await store.get_status(ref) == ActivationStatus.ENABLED
    await store.set_status(ref, ActivationStatus.DISABLED)
    assert await store.get_status(ref) == ActivationStatus.DISABLED


@pytest.mark.asyncio
async def test_statuses_are_scoped_by_kind_connector_and_key(
    activation_store_factory: ActivationStoreFactory, tmp_path: Path
) -> None:
    store = await activation_store_factory(tmp_path)
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
async def test_reconcile_removes_stale_keys_for_kind(
    activation_store_factory: ActivationStoreFactory, tmp_path: Path
) -> None:
    store = await activation_store_factory(tmp_path)
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
async def test_sqlite_store_instances_share_persisted_activation_state(tmp_path: Path) -> None:
    database_path = str(tmp_path / "connectors.sqlite")
    database = (await prepared_sqlite_runtime(database_path)).database
    writer = await create_capability_activation_store(database)
    reader = await create_capability_activation_store(database)
    ref = _ref("github", "search_issues")
    await writer.set_status(ref, ActivationStatus.ENABLED)
    assert await reader.get_status(ref) == ActivationStatus.ENABLED
    await writer.set_status(ref, ActivationStatus.DISABLED)
    assert await reader.get_status(ref) == ActivationStatus.DISABLED
