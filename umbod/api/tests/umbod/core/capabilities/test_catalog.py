from typing import cast

import pytest

from umbod.core.capabilities import (
    AbsentCapabilityOutputSchema,
    CapabilityCatalog,
    CapabilityIdentity,
    CapabilityIdentityConflictError,
    CapabilityNotFoundError,
    InMemoryCapabilityCatalog,
    NormalizedCapability,
    PresentCapabilityOutputSchema,
)


def _capability(operation_name: str = "forecast") -> NormalizedCapability:
    return NormalizedCapability(
        identity=CapabilityIdentity(
            connector_kind="native",
            connector_id="weather",
            capability_kind="tool",
            capability_key=operation_name,
        ),
        title="Weather forecast",
        description="Returns the weather forecast",
        input_schema={"type": "object"},
        output_schema=PresentCapabilityOutputSchema(
            schema={"type": "object", "properties": {"temperature": {"type": "number"}}}
        ),
    )


@pytest.mark.asyncio
async def test_capability_catalog_lists_normalized_capabilities() -> None:
    capability = _capability()
    catalog = cast(CapabilityCatalog, InMemoryCapabilityCatalog((capability,)))

    assert await catalog.list_capabilities() == (capability,)


@pytest.mark.asyncio
async def test_capability_catalog_resolves_by_source_qualified_identity() -> None:
    capability = _capability()
    catalog = cast(CapabilityCatalog, InMemoryCapabilityCatalog((capability,)))

    assert await catalog.resolve(capability.identity) == capability


@pytest.mark.asyncio
async def test_capability_catalog_rejects_missing_identity() -> None:
    catalog = cast(CapabilityCatalog, InMemoryCapabilityCatalog((_capability(),)))
    missing_identity = CapabilityIdentity(
        connector_kind="downstream_mcp",
        connector_id="weather",
        capability_kind="tool",
            capability_key="forecast",
    )

    with pytest.raises(CapabilityNotFoundError) as raised:
        await catalog.resolve(missing_identity)

    assert raised.value.identity == missing_identity


def test_capability_catalog_rejects_duplicate_source_qualified_identities() -> None:
    capability = _capability()

    with pytest.raises(CapabilityIdentityConflictError):
        InMemoryCapabilityCatalog((capability, capability))


def test_present_output_schema_serializes_with_canonical_schema_field() -> None:
    capability = _capability()

    assert capability.model_dump()["output_schema"] == {
        "status": "present",
        "schema": {
            "type": "object",
            "properties": {"temperature": {"type": "number"}},
        },
    }


def test_normalized_capability_preserves_explicit_output_schema_absence() -> None:
    capability = _capability().model_copy(update={"output_schema": AbsentCapabilityOutputSchema()})

    assert capability.output_schema.status == "absent"
