import pytest

from umbod.core.connectors.downstream_mcp.models import DiscoveredToolWithoutOutputSchema, ToolIdentity, ValidatedJsonObject
from umbod.core.connectors.downstream_mcp.personal_tools import ReplacePersonalToolPolicy
from umbod.core.connectors.downstream_mcp.personal_tools.contract_validation import validate_arguments


def approved(schema: ValidatedJsonObject) -> ReplacePersonalToolPolicy:
    tool = DiscoveredToolWithoutOutputSchema(identity=ToolIdentity(connector_id="personal", downstream_name="lookup"), title="Lookup", description="Approved", input_schema=schema)
    return ReplacePersonalToolPolicy(connector_id="personal", expected_revision="unconfigured", tools=(tool,), native_identities=())


@pytest.mark.parametrize("schema", [
    {"$ref": "#/$defs/missing"}, {"$ref": "#missing"}, {"$ref": "#"},
    {"$defs": {"loop": {"$ref": "#/$defs/loop"}}, "$ref": "#/$defs/loop"},
    {"allOf": [{"$ref": "#"}]}, {"anyOf": [{"type": "null"}, {"$ref": "#"}]},
    {"$defs": {"a": {"$ref": "#/$defs/b"}, "b": {"$ref": "#/$defs/a"}}, "$ref": "#/$defs/a"},
    {"$defs": {"a": {"$anchor": "same"}, "b": {"$anchor": "same"}}},
    {"$ref": "#/default", "default": {"type": "string"}},
])
def test_invalid_or_non_descending_references_cannot_be_approved(schema: ValidatedJsonObject) -> None:
    with pytest.raises(ValueError):
        approved(schema)


@pytest.mark.parametrize("schema", [
    {"type": "object", "properties": {"next": {"$ref": "#"}}},
    {"$defs": {"node": {"type": "object", "properties": {"next": {"$ref": "#/$defs/node"}}}}, "$ref": "#/$defs/node"},
    {"$anchor": "node", "type": "object", "properties": {"next": {"$ref": "#node"}}},
    {"$dynamicAnchor": "node", "type": "object", "properties": {"next": {"$dynamicRef": "#node"}}},
])
def test_recursive_data_schemas_remain_supported_without_network(schema: ValidatedJsonObject) -> None:
    command = approved(schema)
    validate_arguments(command.tools[0], {"next": {"next": {}}})


def test_schema_keywords_are_not_interpreted_inside_properties_or_default_data() -> None:
    schema = {"type": "object", "properties": {"$id": {"type": "string"}, "$ref": {"type": "string"}}, "default": {"$id": "ordinary-data", "$ref": "https://not-a-schema.example"}}
    command = approved(schema)
    validate_arguments(command.tools[0], {"$id": "value", "$ref": "text"})


def test_schema_complexity_is_bounded_before_recursive_validation() -> None:
    schema: ValidatedJsonObject = {"type": "string"}
    for _ in range(60):
        schema = {"type": "object", "properties": {"next": schema}}
    with pytest.raises(ValueError):
        approved(schema)
