from unittest.mock import AsyncMock
from uuid import UUID

import pytest

from umbod.core.caching import AsyncRequestCache
from umbod.core.capabilities.cached import CachedCapabilityCatalog, CapabilityCatalogSnapshot
from umbod.core.capabilities.catalog import (
    CapabilityCatalog,
    CapabilityIdentityConflictError,
    CapabilityNotFoundError,
)
from umbod.core.capabilities.domain import (
    CapabilityIdentity,
    CapabilityKind,
    NormalizedCapability,
    PresentCapabilityOutputSchema,
)
from umbod.core.invocation import ConnectorKind
from umbod.infrastructure import create_request_cache


@pytest.fixture
def capability() -> NormalizedCapability:
    return NormalizedCapability(
        identity=CapabilityIdentity(
            connector_kind="native",
            connector_id="connector",
            capability_kind="tool",
            capability_key="key",
        ),
        title="Capability",
        description="A capability",
        input_schema={"properties": {"value": {"type": "string"}}},
        output_schema=PresentCapabilityOutputSchema(
            schema={"properties": {"result": {"type": "string"}}},
        ),
    )


def cached_catalog(source: CapabilityCatalog) -> CapabilityCatalog:
    cache: AsyncRequestCache[UUID, CapabilityCatalogSnapshot] = create_request_cache()
    return CachedCapabilityCatalog(source, cache)


@pytest.mark.asyncio
@pytest.mark.parametrize("resolve_first", [False, True])
async def test_list_and_resolve_share_one_snapshot(
    capability: NormalizedCapability, resolve_first: bool,
) -> None:
    source = AsyncMock(spec=CapabilityCatalog)
    source.list_capabilities.return_value = (capability,)
    underlying: CapabilityCatalog = source
    catalog: CapabilityCatalog = cached_catalog(underlying)

    if resolve_first:
        assert await catalog.resolve(capability.identity) == capability
    assert await catalog.list_capabilities() == (capability,)
    assert await catalog.resolve(capability.identity) == capability
    assert await catalog.list_capabilities() == (capability,)
    source.list_capabilities.assert_awaited_once_with()
    source.resolve.assert_not_awaited()


@pytest.mark.asyncio
async def test_resolve_uses_complete_kind_qualified_identity(
    capability: NormalizedCapability,
) -> None:
    connector_kinds: tuple[ConnectorKind, ...] = ("native", "openapi", "downstream_mcp")
    capability_kinds: tuple[CapabilityKind, ...] = (
        "tool", "prompt", "resource", "resource_template",
    )
    capabilities = tuple(
        capability.model_copy(update={
            "identity": CapabilityIdentity(
                connector_kind=connector_kind,
                connector_id=connector_id,
                capability_kind=capability_kind,
                capability_key=capability_key,
            ),
            "title": f"{connector_kind}/{connector_id}/{capability_kind}/{capability_key}",
        })
        for connector_kind in connector_kinds
        for connector_id in ("first", "second")
        for capability_kind in capability_kinds
        for capability_key in ("first", "second")
    )
    source = AsyncMock(spec=CapabilityCatalog)
    source.list_capabilities.return_value = capabilities
    underlying: CapabilityCatalog = source
    catalog: CapabilityCatalog = cached_catalog(underlying)

    for expected in capabilities:
        assert await catalog.resolve(expected.identity) == expected
    source.list_capabilities.assert_awaited_once_with()
    source.resolve.assert_not_awaited()


@pytest.mark.asyncio
async def test_missing_identity_does_not_reread_snapshot(capability: NormalizedCapability) -> None:
    source = AsyncMock(spec=CapabilityCatalog)
    source.list_capabilities.return_value = ()
    underlying: CapabilityCatalog = source
    catalog: CapabilityCatalog = cached_catalog(underlying)

    for _ in range(2):
        with pytest.raises(CapabilityNotFoundError) as caught:
            await catalog.resolve(capability.identity)
        assert caught.value.identity == capability.identity
    assert await catalog.list_capabilities() == ()
    source.list_capabilities.assert_awaited_once_with()
    source.resolve.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("equal_duplicate", [False, True])
@pytest.mark.parametrize("resolve_first", [False, True])
async def test_duplicate_identity_rejects_snapshot_and_retries(
    capability: NormalizedCapability, equal_duplicate: bool, resolve_first: bool,
) -> None:
    duplicate = capability.model_copy(
        update={} if equal_duplicate else {"title": "Different title"}, deep=True,
    )
    source = AsyncMock(spec=CapabilityCatalog)
    source.list_capabilities.side_effect = [(capability, duplicate), (capability,)]
    underlying: CapabilityCatalog = source
    catalog: CapabilityCatalog = cached_catalog(underlying)

    with pytest.raises(CapabilityIdentityConflictError) as caught:
        if resolve_first:
            await catalog.resolve(capability.identity)
        else:
            await catalog.list_capabilities()
    assert caught.value.identity == capability.identity
    assert await catalog.resolve(capability.identity) == capability
    assert await catalog.list_capabilities() == (capability,)
    assert source.list_capabilities.await_count == 2
    source.resolve.assert_not_awaited()


@pytest.mark.asyncio
async def test_failed_snapshot_load_propagates_and_retries(
    capability: NormalizedCapability,
) -> None:
    source = AsyncMock(spec=CapabilityCatalog)
    source.list_capabilities.side_effect = [RuntimeError("unavailable"), (capability,)]
    underlying: CapabilityCatalog = source
    catalog: CapabilityCatalog = cached_catalog(underlying)

    with pytest.raises(RuntimeError, match="unavailable"):
        await catalog.resolve(capability.identity)
    assert await catalog.list_capabilities() == (capability,)
    assert await catalog.resolve(capability.identity) == capability
    assert source.list_capabilities.await_count == 2
    source.resolve.assert_not_awaited()


def mutate_nested_schemas(capability: NormalizedCapability) -> None:
    properties = capability.input_schema["properties"]
    assert isinstance(properties, dict)
    value = properties["value"]
    assert isinstance(value, dict)
    value["type"] = "number"
    assert isinstance(capability.output_schema, PresentCapabilityOutputSchema)
    output_properties = capability.output_schema.schema_["properties"]
    assert isinstance(output_properties, dict)
    result = output_properties["result"]
    assert isinstance(result, dict)
    result["type"] = "number"


@pytest.mark.asyncio
@pytest.mark.parametrize("mutate_list", [False, True])
async def test_returned_nested_schema_mutation_does_not_poison_snapshot(
    capability: NormalizedCapability, mutate_list: bool,
) -> None:
    source = AsyncMock(spec=CapabilityCatalog)
    source.list_capabilities.return_value = (capability,)
    underlying: CapabilityCatalog = source
    catalog: CapabilityCatalog = cached_catalog(underlying)
    returned = (
        (await catalog.list_capabilities())[0]
        if mutate_list else await catalog.resolve(capability.identity)
    )

    mutate_nested_schemas(returned)

    assert await catalog.list_capabilities() == (capability,)
    assert await catalog.resolve(capability.identity) == capability
    source.list_capabilities.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_underlying_nested_mutation_does_not_change_captured_snapshot(
    capability: NormalizedCapability,
) -> None:
    expected = capability.model_copy(deep=True)
    source = AsyncMock(spec=CapabilityCatalog)
    source.list_capabilities.return_value = (capability,)
    underlying: CapabilityCatalog = source
    catalog: CapabilityCatalog = cached_catalog(underlying)
    assert await catalog.list_capabilities() == (expected,)

    mutate_nested_schemas(capability)

    assert await catalog.list_capabilities() == (expected,)
    assert await catalog.resolve(capability.identity) == expected
    source.list_capabilities.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_wrappers_are_isolated_with_shared_typed_cache(
    capability: NormalizedCapability,
) -> None:
    changed = capability.model_copy(update={"title": "Changed"})
    source = AsyncMock(spec=CapabilityCatalog)
    source.list_capabilities.side_effect = [(capability,), (changed,)]
    underlying: CapabilityCatalog = source
    cache: AsyncRequestCache[UUID, CapabilityCatalogSnapshot] = create_request_cache()
    first: CapabilityCatalog = CachedCapabilityCatalog(underlying, cache)
    second: CapabilityCatalog = CachedCapabilityCatalog(underlying, cache)

    for _ in range(2):
        assert await first.list_capabilities() == (capability,)
        assert await second.list_capabilities() == (changed,)
        assert await first.resolve(capability.identity) == capability
        assert await second.resolve(capability.identity) == changed
    assert source.list_capabilities.await_count == 2
    source.resolve.assert_not_awaited()


@pytest.mark.asyncio
async def test_fresh_request_cache_captures_current_catalog(
    capability: NormalizedCapability,
) -> None:
    changed = capability.model_copy(update={"title": "Changed"})
    source = AsyncMock(spec=CapabilityCatalog)
    source.list_capabilities.side_effect = [(capability,), (changed,)]
    underlying: CapabilityCatalog = source

    for expected in (capability, changed):
        catalog: CapabilityCatalog = cached_catalog(underlying)
        assert await catalog.list_capabilities() == (expected,)
        assert await catalog.resolve(expected.identity) == expected
    assert source.list_capabilities.await_count == 2
    source.resolve.assert_not_awaited()
