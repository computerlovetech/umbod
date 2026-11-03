import math

import pytest
from pydantic import TypeAdapter, ValidationError

from umbod.core.connectors.downstream_mcp.models import (
    DiscoveredTool,
    DiscoveredToolWithOutputSchema,
    DiscoveredToolWithoutOutputSchema,
    NoAuthConnectorDefinition,
    ToolIdentity,
)


DISCOVERED_TOOL_ADAPTER = TypeAdapter(DiscoveredTool)


@pytest.mark.asyncio
async def test_connector_definition_requires_valid_capability_description() -> None:
    valid = NoAuthConnectorDefinition(
        connector_id="alpha",
        display_name="Alpha",
        capability_description="  Search customer records  ",
        endpoint_url="https://example.test/mcp",
    )
    assert valid.capability_description == "Search customer records"
    for invalid in ("", "   ", "x" * 301, "line\nbreak"):
        with pytest.raises(ValidationError):
            NoAuthConnectorDefinition(
                connector_id="alpha",
                display_name="Alpha",
                capability_description=invalid,
                endpoint_url="https://example.test/mcp",
            )


@pytest.mark.asyncio
async def test_discovered_tool_preserves_mcp_proxy_metadata() -> None:
    tool = DiscoveredToolWithOutputSchema(
        identity=ToolIdentity(connector_id="alpha", downstream_name="lookup"),
        title="Lookup",
        description="Looks up a record",
        input_schema={"type": "object", "properties": {"id": {"type": "string"}}},
        output_schema={"type": "object"},
        annotations={"readOnlyHint": True, "title": "Lookup"},
        icons=({"src": "https://example.test/icon.svg", "mimeType": "image/svg+xml"},),
        meta={"vendor": {"category": "search"}},
        execution={"taskSupport": "optional"},
    )

    restored = DISCOVERED_TOOL_ADAPTER.validate_json(DISCOVERED_TOOL_ADAPTER.dump_json(tool))

    assert restored == tool


@pytest.mark.asyncio
async def test_discovered_tool_models_output_schema_absence_explicitly() -> None:
    tool = DiscoveredToolWithoutOutputSchema(
        identity=ToolIdentity(connector_id="alpha", downstream_name="notify"),
        title="Notify",
        description="Sends a notification",
        input_schema={"type": "object"},
    )

    assert tool.output_schema_status == "absent"
    assert "output_schema" not in tool.model_fields_set


@pytest.mark.parametrize(
    "field,value",
    [
        ("input_schema", {"invalid": object()}),
        ("input_schema", {"invalid": math.nan}),
        ("annotations", {"invalid": object()}),
        ("meta", {"invalid": object()}),
        ("execution", {"invalid": object()}),
        ("icons", ({"invalid": object()},)),
    ],
)
@pytest.mark.asyncio
async def test_discovered_tool_rejects_json_incompatible_metadata(
    field: str, value: object
) -> None:
    payload: dict[str, object] = {
        "identity": {"connector_id": "alpha", "downstream_name": "lookup"},
        "title": "Lookup",
        "description": "Looks up a record",
        "input_schema": {"type": "object"},
        "output_schema_status": "absent",
        field: value,
    }

    with pytest.raises((ValidationError, ValueError)):
        DISCOVERED_TOOL_ADAPTER.validate_python(payload)


@pytest.mark.parametrize(
    "endpoint_url",
    [
        "http://example.test/mcp",
        "ftp://example.test/mcp",
        "https://user:password@example.test/mcp",
        "https://example.test/mcp#fragment",
        "https://exa mple.test/mcp",
        "https://example.test:invalid/mcp",
        "https:///mcp",
        "https://",
    ],
)
@pytest.mark.asyncio
async def test_connector_definition_rejects_unsafe_endpoint_urls(endpoint_url: str) -> None:
    with pytest.raises(ValidationError):
        NoAuthConnectorDefinition(
            connector_id="alpha", display_name="Alpha", endpoint_url=endpoint_url
        )


@pytest.mark.parametrize(
    "endpoint_url",
    [
        "https://example.test/mcp",
        "http://localhost:8000/mcp",
        "http://127.0.0.1:8000/mcp",
        "http://[::1]:8000/mcp",
    ],
)
@pytest.mark.asyncio
async def test_connector_definition_accepts_https_and_loopback_development_http(
    endpoint_url: str,
) -> None:
    definition = NoAuthConnectorDefinition(
        connector_id="alpha", display_name="Alpha", endpoint_url=endpoint_url
    )

    assert definition.endpoint_url == endpoint_url
