import asyncio
from unittest.mock import AsyncMock, Mock

import pytest

from messaging.in_memory import InMemoryEventCheckpointStoreFactory, InMemoryEventCheckpointStoreMessages
from umbod.core.filesystem.authorization import FilesystemAuthorizationReader, FilesystemOperation
from umbod.mcp.filesystem.discovery import FilesystemToolVisibility
from umbod.mcp.filesystem.discovery import FilesystemDiscoveryRuntime
from umbod.mcp.messaging import RuntimeProjectionHealth, RuntimeProjectionSynchronizer
from umbod.mcp.messaging.transport import DatabaseProjectionEventReader

from .conftest import FilesystemMcp
from .test_visibility import BOOTSTRAP_TOOLS, listed_tools, shared_namespace, save_namespace_access, select_caller


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [RuntimeError("projection failed"), asyncio.CancelledError()])
async def test_failed_or_cancelled_refresh_hides_populated_runtime_until_recovery(
    filesystem_mcp: FilesystemMcp, failure: BaseException,
) -> None:
    snapshot = filesystem_mcp.runtime.capture()
    reader = Mock(spec=FilesystemAuthorizationReader)
    reader.read = AsyncMock(side_effect=[snapshot, failure, snapshot])
    runtime = FilesystemDiscoveryRuntime(reader)
    visibility = FilesystemToolVisibility(filesystem_mcp.callers, runtime)
    assert await visibility.capture() == frozenset({FilesystemOperation.HOME})
    await runtime.reconcile()
    permitted = await visibility.capture()
    assert permitted
    with pytest.raises(type(failure)):
        await runtime.reconcile()
    assert await visibility.capture() == frozenset({FilesystemOperation.HOME})
    await runtime.reconcile()
    assert await visibility.capture() == permitted


@pytest.mark.asyncio
async def test_committed_policy_event_refreshes_public_discovery_through_database_transport(
    filesystem_mcp: FilesystemMcp,
) -> None:
    namespace = await shared_namespace(filesystem_mcp)
    select_caller(filesystem_mcp, "bob", (namespace.groups[0].group_id,))
    health = RuntimeProjectionHealth()
    checkpoints = InMemoryEventCheckpointStoreFactory(InMemoryEventCheckpointStoreMessages()).create()
    synchronizer = RuntimeProjectionSynchronizer(
        DatabaseProjectionEventReader(filesystem_mcp.database), checkpoints,
        filesystem_mcp.runtime.reconcile, health, interval_seconds=1.0, batch_limit=100,
    )
    await synchronizer.bootstrap()
    assert await listed_tools(filesystem_mcp) == BOOTSTRAP_TOOLS
    await save_namespace_access(filesystem_mcp, namespace, None)
    assert await listed_tools(filesystem_mcp) == BOOTSTRAP_TOOLS
    assert await synchronizer.poll_once()
    assert await listed_tools(filesystem_mcp) == {"filesystem_browse"}
    assert health.ready


@pytest.mark.asyncio
async def test_real_policy_change_during_bootstrap_hydration_is_replayed_before_ready(
    filesystem_mcp: FilesystemMcp,
) -> None:
    namespace = await shared_namespace(filesystem_mcp)
    select_caller(filesystem_mcp, "bob", (namespace.groups[0].group_id,))
    health = RuntimeProjectionHealth()
    reconciliations = 0

    async def reconcile() -> None:
        nonlocal reconciliations
        await filesystem_mcp.runtime.reconcile()
        reconciliations += 1
        if reconciliations == 1:
            await save_namespace_access(filesystem_mcp, namespace, None)

    checkpoints = InMemoryEventCheckpointStoreFactory(InMemoryEventCheckpointStoreMessages()).create()
    synchronizer = RuntimeProjectionSynchronizer(
        DatabaseProjectionEventReader(filesystem_mcp.database), checkpoints,
        reconcile, health, interval_seconds=1.0, batch_limit=100,
    )
    await synchronizer.bootstrap()
    assert reconciliations == 2
    assert health.ready
    assert await listed_tools(filesystem_mcp) == {"filesystem_browse"}
