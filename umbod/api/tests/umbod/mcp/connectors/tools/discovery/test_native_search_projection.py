import asyncio
from collections.abc import Awaitable, Callable

import pytest

from umbod.core.capabilities import (
    AbsentCapabilityOutputSchema,
    CapabilityAvailability,
    CapabilityIdentity,
    NormalizedCapability,
    UnrestrictedCapabilityActivation,
    UnrestrictedCapabilityPermissionPolicy,
    UnrestrictedCapabilityReadiness,
)
from umbod.core.capabilities.descriptions import SystemConnectorCapabilityDescriptionOverrideStore
from umbod.core.connectors.native.capabilities import NativeCapabilityBinding, NativeCapabilityCatalog
from umbod.core.connectors.native.runtime.tools import ConnectorToolMapping
from umbod.mcp.connectors.native.tools.infrastructure.authorization import UnrestrictedConnectorTools
from umbod.mcp.connectors.native.tools.invocation.runner import ConnectorToolInvocationRunner
from umbod.mcp.connectors.native.tools.runtime.native_capabilities import (
    NativeCapabilityRuntime,
    NativeCapabilitySearch,
)


class CallbackCapabilityPublication:
    def __init__(self, check: Callable[[CapabilityIdentity], Awaitable[bool]]) -> None:
        self.check = check

    async def is_published(self, identity: CapabilityIdentity) -> bool:
        return await self.check(identity)


async def _available(identity: CapabilityIdentity) -> bool:
    return True


def _unexpected_invoker(mapping: ConnectorToolMapping) -> ConnectorToolInvocationRunner:
    raise AssertionError("Discovery must not construct an invoker")


async def _unexpected_admission(identity: CapabilityIdentity) -> None:
    raise AssertionError("Discovery must not admit execution")


@pytest.fixture
def search_dependencies() -> CallbackCapabilityPublication:
    return CallbackCapabilityPublication(_available)


def _search(publication: CallbackCapabilityPublication) -> NativeCapabilitySearch:
    capability = NormalizedCapability(
        identity=CapabilityIdentity(
            connector_kind="native", connector_id="slack", capability_kind="tool",
            capability_key="list_channels",
        ),
        title="Channels", description="List channels",
        input_schema={"type": "object", "properties": {"filter": {"enum": ["original"]}}},
        output_schema=AbsentCapabilityOutputSchema(),
    )
    catalog = NativeCapabilityCatalog((NativeCapabilityBinding(
        capability=capability, mapping=None, public_tool_name="slack_list_channels",
    ),))
    availability = CapabilityAvailability(
        publication,
        UnrestrictedCapabilityActivation(),
        UnrestrictedCapabilityReadiness(),
        UnrestrictedCapabilityPermissionPolicy(),
    )
    runtime = NativeCapabilityRuntime(
        catalog, availability, _unexpected_invoker, _unexpected_admission,
    )
    return NativeCapabilitySearch(
        runtime, {"slack": "Slack"}, {"slack": "Channel access"},
        SystemConnectorCapabilityDescriptionOverrideStore(),
    )


async def _cancel_tasks(tasks: list[asyncio.Task[None]]) -> None:
    for task in tasks:
        if not task.done():
            task.cancel()
    await asyncio.wait_for(asyncio.gather(*tasks, return_exceptions=True), timeout=5)


@pytest.mark.asyncio
async def test_independent_native_refreshes_are_serialized(
    search_dependencies: CallbackCapabilityPublication,
) -> None:
    search = _search(search_dependencies)
    started = asyncio.Event()
    release = asyncio.Event()
    queued = asyncio.Event()
    calls = 0

    async def available(identity: CapabilityIdentity) -> bool:
        nonlocal calls
        calls += 1
        if calls == 1:
            started.set()
            await asyncio.wait_for(release.wait(), timeout=5)
            return True
        return False

    async def refresh_again() -> None:
        queued.set()
        await search.refresh()

    search_dependencies.check = available
    tasks: list[asyncio.Task[None]] = []
    try:
        first = asyncio.create_task(asyncio.wait_for(search.refresh(), timeout=5))
        tasks.append(first)
        await asyncio.wait_for(started.wait(), timeout=5)
        second = asyncio.create_task(asyncio.wait_for(refresh_again(), timeout=5))
        tasks.append(second)
        await asyncio.wait_for(queued.wait(), timeout=5)
        assert calls == 1
        assert await asyncio.wait_for(search.candidates(UnrestrictedConnectorTools()), timeout=5) == []
        release.set()
        await asyncio.wait_for(asyncio.gather(first, second), timeout=5)
        assert calls == 2
        assert await asyncio.wait_for(search.candidates(UnrestrictedConnectorTools()), timeout=5) == []
    finally:
        await _cancel_tasks(tasks)


@pytest.mark.asyncio
async def test_independent_native_refresh_failure_and_cancellation_allow_retry(
    search_dependencies: CallbackCapabilityPublication,
) -> None:
    search = _search(search_dependencies)
    await asyncio.wait_for(search.refresh(), timeout=5)
    scope = UnrestrictedConnectorTools()
    original = await asyncio.wait_for(search.candidates(scope), timeout=5)
    started = asyncio.Event()
    release = asyncio.Event()

    async def available(identity: CapabilityIdentity) -> bool:
        started.set()
        await asyncio.wait_for(release.wait(), timeout=5)
        return False

    async def unavailable(identity: CapabilityIdentity) -> bool:
        raise RuntimeError("unavailable")

    search_dependencies.check = available
    tasks: list[asyncio.Task[None]] = []
    try:
        task = asyncio.create_task(asyncio.wait_for(search.refresh(), timeout=5))
        tasks.append(task)
        await asyncio.wait_for(started.wait(), timeout=5)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, timeout=5)
    finally:
        await _cancel_tasks(tasks)
    assert await asyncio.wait_for(search.candidates(scope), timeout=5) == original
    search_dependencies.check = unavailable
    with pytest.raises(RuntimeError, match="unavailable"):
        await asyncio.wait_for(search.refresh(), timeout=5)
    assert await asyncio.wait_for(search.candidates(scope), timeout=5) == []
    search_dependencies.check = _available
    await asyncio.wait_for(search.refresh(), timeout=5)
    assert await asyncio.wait_for(search.candidates(scope), timeout=5) == original


@pytest.mark.asyncio
async def test_native_candidate_schema_mutation_does_not_change_future_discovery(
    search_dependencies: CallbackCapabilityPublication,
) -> None:
    search = _search(search_dependencies)
    await asyncio.wait_for(search.refresh(), timeout=5)
    scope = UnrestrictedConnectorTools()
    first = await asyncio.wait_for(search.candidates(scope), timeout=5)
    first[0].input_schema["properties"]["filter"]["enum"].append("caller mutation")
    second = await asyncio.wait_for(search.candidates(scope), timeout=5)
    assert second[0].input_schema["properties"]["filter"]["enum"] == ["original"]
