import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from umbod.core.capabilities import AbsentCapabilityOutputSchema, CapabilityIdentity, NormalizedCapability
from umbod.mcp.connectors.native.tools.infrastructure.authorization import UnrestrictedConnectorTools
from umbod.mcp.connectors.native.tools.runtime.native_capabilities import NativeCapabilitySearch


@pytest.fixture
def search_dependencies() -> SimpleNamespace:
    capability = NormalizedCapability(
        identity=CapabilityIdentity(
            connector_kind="native", connector_id="slack", capability_kind="tool",
            capability_key="list_channels",
        ),
        title="Channels", description="List channels",
        input_schema={"type": "object", "properties": {"filter": {"enum": ["original"]}}},
        output_schema=AbsentCapabilityOutputSchema(),
    )
    binding = SimpleNamespace(capability=capability, public_tool_name="slack_list_channels")
    catalog = SimpleNamespace(
        list_capabilities=AsyncMock(return_value=(capability,)),
        resolve_binding=lambda identity: binding,
    )
    runtime = SimpleNamespace(catalog=catalog, is_available=AsyncMock(return_value=True))
    descriptions = SimpleNamespace(get_many=AsyncMock(return_value=(object(),)))
    return SimpleNamespace(runtime=runtime, descriptions=descriptions)


def _search(dependencies: SimpleNamespace) -> NativeCapabilitySearch:
    return NativeCapabilitySearch(
        dependencies.runtime, {"slack": "Slack"}, {"slack": "Channel access"},
        dependencies.descriptions,
    )


@pytest.mark.asyncio
async def test_independent_native_refreshes_are_serialized(search_dependencies: SimpleNamespace) -> None:
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
            await release.wait()
            return True
        return False

    search_dependencies.runtime.is_available.side_effect = available
    search_dependencies.descriptions.get_many.side_effect = lambda keys: tuple(object() for _ in keys)
    first = asyncio.create_task(search.refresh())
    await started.wait()

    async def refresh_again() -> None:
        queued.set()
        await search.refresh()

    second = asyncio.create_task(refresh_again())
    await queued.wait()
    assert calls == 1
    assert await search.candidates(UnrestrictedConnectorTools()) == []
    release.set()
    await asyncio.gather(first, second)
    assert calls == 2
    assert await search.candidates(UnrestrictedConnectorTools()) == []


@pytest.mark.asyncio
async def test_independent_native_refresh_failure_and_cancellation_allow_retry(
    search_dependencies: SimpleNamespace,
) -> None:
    search = _search(search_dependencies)
    await search.refresh()
    scope = UnrestrictedConnectorTools()
    original = await search.candidates(scope)
    started = asyncio.Event()
    release = asyncio.Event()

    async def available(identity: CapabilityIdentity) -> bool:
        started.set()
        await release.wait()
        return False

    search_dependencies.runtime.is_available.side_effect = available
    task = asyncio.create_task(search.refresh())
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert await search.candidates(scope) == original
    search_dependencies.runtime.is_available.side_effect = RuntimeError("unavailable")
    with pytest.raises(RuntimeError, match="unavailable"):
        await search.refresh()
    assert await search.candidates(scope) == []
    search_dependencies.runtime.is_available.side_effect = None
    await search.refresh()
    assert await search.candidates(scope) == original


@pytest.mark.asyncio
async def test_native_candidate_schema_mutation_does_not_change_future_discovery(
    search_dependencies: SimpleNamespace,
) -> None:
    search = _search(search_dependencies)
    await search.refresh()
    scope = UnrestrictedConnectorTools()
    first = await search.candidates(scope)
    first[0].input_schema["properties"]["filter"]["enum"].append("caller mutation")
    second = await search.candidates(scope)
    assert second[0].input_schema["properties"]["filter"]["enum"] == ["original"]
