import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from umbod.core.capabilities import AbsentCapabilityOutputSchema, CapabilityCatalog, CapabilityIdentity, NormalizedCapability, PresentCapabilityOutputSchema
from umbod.core.permissions.domain import GroupPermissionSet
from umbod.mcp.connectors.native.tools.discovery.openapi import NormalizedOpenApiConnectorDiscovery
from umbod.mcp.connectors.openapi import discovery_runtime
from umbod.mcp.connectors.openapi.discovery_runtime import AuthorizedOpenApiDiscoveryCatalog, OpenApiDiscoveryProjection


def _capability() -> NormalizedCapability:
    return NormalizedCapability(
        identity=CapabilityIdentity(
            connector_kind="openapi", connector_id="inventory",
            capability_kind="tool", capability_key="getItem",
        ),
        title="Inventory item", description="Read inventory", input_schema={"type": "object"},
        output_schema=AbsentCapabilityOutputSchema(),
        connector_display_name="Inventory", connector_capability_description="Manage inventory",
    )


@pytest.mark.asyncio
async def test_initialized_projection_discovery_never_reloads_structure_and_uses_current_grants(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = AsyncMock(return_value=(_capability(),))
    monkeypatch.setattr(discovery_runtime, "get_openapi_connector_store", AsyncMock(return_value=object()))
    monkeypatch.setattr(discovery_runtime.StoreBackedOpenApiCapabilityCatalog, "list_capabilities", source)
    descriptions = SimpleNamespace(get_many=AsyncMock(return_value=(object(),)))
    server = SimpleNamespace(capability_description_overrides=descriptions)
    await discovery_runtime.initialize_openapi_discovery(server)
    projection: OpenApiDiscoveryProjection = server.openapi_discovery_catalog
    source.side_effect = AssertionError("catalog reads during discovery")
    descriptions.get_many.side_effect = AssertionError("description reads during discovery")
    monkeypatch.setattr(discovery_runtime, "get_openapi_connector_store", AsyncMock(
        side_effect=AssertionError("connector reads during discovery"),
    ))
    permissions = SimpleNamespace(list_group_permissions=AsyncMock(return_value=GroupPermissionSet(
        group_id="engineering", connector_ids=("inventory",), capabilities=(),
    )))
    catalog: CapabilityCatalog = AuthorizedOpenApiDiscoveryCatalog(
        projection.snapshot(), permissions, ("engineering",),
    )
    discovery = NormalizedOpenApiConnectorDiscovery(catalog)
    assert len((await discovery.enumerate()).candidates) == 1
    assert len((await discovery.search("inventory")).candidates) == 1
    permissions.list_group_permissions.return_value = GroupPermissionSet(
        group_id="engineering", connector_ids=(), capabilities=(),
    )
    assert (await discovery.enumerate()).candidates == ()
    assert (await discovery.search("inventory")).candidates == ()
    source.assert_awaited_once()


@pytest.mark.asyncio
async def test_reconciliation_replaces_snapshot_and_failed_refresh_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = AsyncMock(return_value=(_capability(),))
    monkeypatch.setattr(discovery_runtime, "get_openapi_connector_store", AsyncMock(return_value=object()))
    monkeypatch.setattr(discovery_runtime.StoreBackedOpenApiCapabilityCatalog, "list_capabilities", source)
    descriptions = SimpleNamespace(get_many=AsyncMock(return_value=(object(),)))
    server = SimpleNamespace(capability_description_overrides=descriptions)
    await discovery_runtime.initialize_openapi_discovery(server)
    projection: OpenApiDiscoveryProjection = server.openapi_discovery_catalog
    original = projection.snapshot()
    source.return_value = ()
    descriptions.get_many.return_value = ()
    await discovery_runtime.reconcile_openapi_discovery(server)
    assert projection.snapshot() == ()
    assert len(original) == 1
    source.side_effect = RuntimeError("unavailable")
    with pytest.raises(RuntimeError, match="unavailable"):
        await discovery_runtime.reconcile_openapi_discovery(server)
    assert projection.snapshot() == ()
    source.side_effect = None
    source.return_value = (_capability(),)
    descriptions.get_many.return_value = (object(),)
    await projection.reconcile(server)
    assert len(projection.snapshot()) == 1


@pytest.mark.asyncio
async def test_overlapping_reconciliations_load_and_publish_in_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    started = asyncio.Event()
    release = asyncio.Event()
    queued = asyncio.Event()
    calls = 0

    async def load() -> tuple[NormalizedCapability, ...]:
        nonlocal calls
        calls += 1
        if calls == 1:
            started.set()
            await release.wait()
            return (_capability(),)
        return ()

    monkeypatch.setattr(discovery_runtime, "get_openapi_connector_store", AsyncMock(return_value=object()))
    monkeypatch.setattr(discovery_runtime.StoreBackedOpenApiCapabilityCatalog, "list_capabilities", AsyncMock(side_effect=load))
    server = SimpleNamespace(capability_description_overrides=SimpleNamespace(
        get_many=AsyncMock(side_effect=lambda keys: tuple(object() for _ in keys)),
    ))
    projection: OpenApiDiscoveryProjection = discovery_runtime.InMemoryOpenApiDiscoveryProjection()
    first = asyncio.create_task(projection.reconcile(server))
    await started.wait()

    async def reconcile_again() -> None:
        queued.set()
        await projection.reconcile(server)

    second = asyncio.create_task(reconcile_again())
    await queued.wait()
    assert calls == 1
    assert projection.snapshot() == ()
    release.set()
    await asyncio.gather(first, second)
    assert calls == 2
    assert projection.snapshot() == ()


@pytest.mark.asyncio
async def test_cancelled_refresh_preserves_complete_snapshot_and_allows_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = AsyncMock(return_value=(_capability(),))
    monkeypatch.setattr(discovery_runtime, "get_openapi_connector_store", AsyncMock(return_value=object()))
    monkeypatch.setattr(discovery_runtime.StoreBackedOpenApiCapabilityCatalog, "list_capabilities", source)
    server = SimpleNamespace(capability_description_overrides=SimpleNamespace(
        get_many=AsyncMock(side_effect=lambda keys: tuple(object() for _ in keys)),
    ))
    await discovery_runtime.initialize_openapi_discovery(server)
    projection: OpenApiDiscoveryProjection = server.openapi_discovery_catalog
    original = projection.snapshot()
    started = asyncio.Event()
    release = asyncio.Event()

    async def blocked_load() -> tuple[NormalizedCapability, ...]:
        started.set()
        await release.wait()
        return ()

    source.side_effect = blocked_load
    task = asyncio.create_task(projection.reconcile(server))
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert projection.snapshot() == original
    source.side_effect = None
    source.return_value = ()
    await projection.reconcile(server)
    assert projection.snapshot() == ()


@pytest.mark.asyncio
async def test_openapi_projection_and_authorized_catalog_isolate_mutable_schemas(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    capability = _capability().model_copy(update={
        "input_schema": {"properties": {"filter": {"enum": ["original"]}}},
        "output_schema": PresentCapabilityOutputSchema(schema={"properties": {"items": {"type": "array"}}}),
    })
    monkeypatch.setattr(discovery_runtime, "get_openapi_connector_store", AsyncMock(return_value=object()))
    monkeypatch.setattr(discovery_runtime.StoreBackedOpenApiCapabilityCatalog, "list_capabilities", AsyncMock(return_value=(capability,)))
    server = SimpleNamespace(capability_description_overrides=SimpleNamespace(get_many=AsyncMock(return_value=(object(),))))
    await discovery_runtime.initialize_openapi_discovery(server)
    projection: OpenApiDiscoveryProjection = server.openapi_discovery_catalog
    first = projection.snapshot()
    first[0].input_schema["properties"]["filter"]["enum"].append("mutated")
    first[0].output_schema.schema_["properties"]["items"]["type"] = "string"
    assert projection.snapshot()[0].input_schema == capability.input_schema
    assert projection.snapshot()[0].output_schema == capability.output_schema
    permissions = SimpleNamespace(list_group_permissions=AsyncMock(return_value=GroupPermissionSet(
        group_id="engineering", connector_ids=("inventory",), capabilities=(),
    )))
    snapshot = projection.snapshot()
    catalog: CapabilityCatalog = AuthorizedOpenApiDiscoveryCatalog(snapshot, permissions, ("engineering",))
    snapshot[0].input_schema["properties"]["filter"]["enum"].append("after-construction")
    listed = await catalog.list_capabilities()
    assert listed[0].input_schema == capability.input_schema
    listed[0].input_schema["properties"]["filter"]["enum"].append("caller")
    listed[0].output_schema.schema_["properties"]["items"]["type"] = "string"
    resolved = await catalog.resolve(capability.identity)
    assert resolved.input_schema == capability.input_schema
    assert resolved.output_schema == capability.output_schema
    discovery = NormalizedOpenApiConnectorDiscovery(catalog)
    result = await discovery.enumerate()
    result.candidates[0].input_schema["properties"]["filter"]["enum"].append("search-caller")
    assert (await discovery.search("inventory")).candidates[0].input_schema == capability.input_schema
