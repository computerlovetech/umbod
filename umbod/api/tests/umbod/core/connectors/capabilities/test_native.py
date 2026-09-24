from typing import cast

import pytest

from umbod.core.capabilities import CapabilityCatalog
from umbod.core.connectors.native.capabilities import NativeCapabilityCatalog
from umbod.core.connectors.native.runtime.tools import ConcreteConnectorToolMapping
from umbod.core.connectors.native.tools.descriptions import ConnectorToolParameterDescription
from umbod.core.capabilities.tools.output_schema import AbsentConnectorToolOutputSchema, PresentConnectorToolOutputSchema


def _operation(city: str) -> dict[str, object]:
    return {"city": city}


@pytest.mark.asyncio
async def test_native_catalog_normalizes_runtime_mapping() -> None:
    mapping = ConcreteConnectorToolMapping(
        connector_id="weather",
        tool_name_prefix="Weather-API",
        operation_name="get/forecast",
        description="Returns a forecast",
        operation=_operation,
        parameters={
            "type": "object",
            "properties": {"city": {"type": "string"}},
            "required": ["city"],
        },
        output_schema=PresentConnectorToolOutputSchema(
            {"type": "object", "properties": {"city": {"type": "string"}}}
        ),
    )
    catalog = cast(CapabilityCatalog, NativeCapabilityCatalog.from_mappings((mapping,)))

    capability = (await catalog.list_capabilities())[0]

    assert capability.identity.connector_kind == "native"
    assert capability.identity.connector_id == "weather"
    assert capability.identity.capability_key == "get/forecast"
    assert capability.title == "get/forecast"
    assert capability.description == "Returns a forecast"
    assert capability.input_schema == mapping.parameters
    assert capability.output_schema.status == "present"
    assert capability.output_schema.schema_ == mapping.output_schema.output_schema


@pytest.mark.asyncio
async def test_native_catalog_normalizes_parameter_descriptions_and_absent_output() -> None:
    mapping = ConcreteConnectorToolMapping(
        connector_id="weather",
        tool_name_prefix="weather",
        operation_name="forecast",
        description="Returns a forecast",
        operation=_operation,
        parameters=[
            ConnectorToolParameterDescription(
                name="city",
                type="string",
                description="Forecast city",
                required=True,
            )
        ],
        output_schema=AbsentConnectorToolOutputSchema(),
    )
    catalog = cast(CapabilityCatalog, NativeCapabilityCatalog.from_mappings((mapping,)))

    capability = (await catalog.list_capabilities())[0]

    assert capability.input_schema == {
        "type": "object",
        "properties": {"city": {"type": "string", "description": "Forecast city"}},
        "required": ["city"],
    }
    assert capability.output_schema.status == "absent"
