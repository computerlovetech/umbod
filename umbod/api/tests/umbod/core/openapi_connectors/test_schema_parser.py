import pytest

from umbod.core.connectors.openapi.importing import (
    OpenApiSchemaParser,
    SameDocumentJsonPointerResolver,
    ValidationIssues,
)
from umbod.core.connectors.openapi.models import (
    BooleanSchema,
    CompositionSchema,
    ObjectSchema,
    PrimitiveSchema,
)


@pytest.mark.parametrize(
    ("raw_schema", "expected_values"),
    [
        ({"type": "string", "enum": ["todo", "done"]}, ("todo", "done")),
        ({"type": "integer", "enum": [1, 2]}, (1, 2)),
    ],
    ids=["string", "integer"],
)
def test_parses_primitive_enum_values(
    raw_schema: dict[str, object],
    expected_values: tuple[object, ...],
) -> None:
    issues = ValidationIssues()
    parser = OpenApiSchemaParser(
        issues, SameDocumentJsonPointerResolver({}, maximum_depth=64).resolve
    )

    parsed = parser.parse(raw_schema, ("schema",))

    assert isinstance(parsed, PrimitiveSchema)
    assert parsed.enum == expected_values
    assert issues.values == []


def test_parses_referenced_nested_property_enum_values() -> None:
    document = {
        "components": {
            "schemas": {
                "Status": {
                    "type": "string",
                    "description": "Current workflow status.",
                    "enum": ["todo", "done"],
                },
                "Task": {
                    "type": "object",
                    "properties": {
                        "status": {"$ref": "#/components/schemas/Status"},
                    },
                    "required": ["status"],
                },
            },
        },
    }
    issues = ValidationIssues()
    parser = OpenApiSchemaParser(
        issues, SameDocumentJsonPointerResolver(document, maximum_depth=64).resolve
    )

    parsed = parser.parse({"$ref": "#/components/schemas/Task"}, ("schema",))

    assert isinstance(parsed, ObjectSchema)
    status = parsed.properties["status"]
    assert isinstance(status, PrimitiveSchema)
    assert status.enum == ("todo", "done")
    assert status.description == "Current workflow status."
    assert issues.values == []


def test_parses_boolean_schema_and_composition() -> None:
    document = {"components": {"schemas": {"Name": {"type": ["string", "null"]}}}}
    issues = ValidationIssues()
    parser = OpenApiSchemaParser(
        issues, SameDocumentJsonPointerResolver(document, maximum_depth=64).resolve
    )

    boolean_schema = parser.parse(False, ("schema",))
    composition = parser.parse(
        {"allOf": [{"$ref": "#/components/schemas/Name"}, {"not": {"const": ""}}]},
        ("schema",),
    )

    assert boolean_schema == BooleanSchema(allows_values=False)
    assert isinstance(composition, CompositionSchema)
    assert composition.operator == "allOf"
    assert isinstance(composition.schemas[1], CompositionSchema)
    assert issues.values == []


def test_parses_object_additional_properties_and_recursive_reference_safely() -> None:
    document = {
        "components": {
            "schemas": {
                "Node": {
                    "type": "object",
                    "properties": {"child": {"$ref": "#/components/schemas/Node"}},
                    "additionalProperties": False,
                }
            }
        }
    }
    issues = ValidationIssues()
    parser = OpenApiSchemaParser(
        issues, SameDocumentJsonPointerResolver(document, maximum_depth=64).resolve
    )

    parsed = parser.parse({"$ref": "#/components/schemas/Node"}, ("schema",))

    assert isinstance(parsed, ObjectSchema)
    assert parsed.additional_properties is False
    assert parsed.properties["child"].type == "unspecified"
    assert issues.values == []
