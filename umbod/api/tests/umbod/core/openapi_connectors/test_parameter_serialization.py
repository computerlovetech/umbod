import pytest

from umbod.core.connectors.openapi.models import (
    ArraySchema,
    ObjectSchema,
    OpenApiParameter,
    PrimitiveSchema,
)
from umbod.core.connectors.openapi.execution import (
    OpenApiParameterSerializer,
    OpenApiValueValidator,
    SUPPORTED_PARAMETER_SERIALIZATION,
)


def _primitive() -> PrimitiveSchema:
    return PrimitiveSchema(type="string", format="", description="")


def _schema_and_value(kind: str) -> tuple[PrimitiveSchema | ArraySchema | ObjectSchema, object]:
    primitive = _primitive()
    if kind == "array":
        return ArraySchema(items=primitive, description=""), ["a&b", "c/d"]
    if kind == "object":
        return ObjectSchema(properties={"a&b": primitive}, required=("a&b",), description=""), {
            "a&b": "c=d"
        }
    return primitive, "a&b"


@pytest.mark.parametrize(
    ("rule", "kind"),
    [
        (rule, kind)
        for rule in SUPPORTED_PARAMETER_SERIALIZATION
        for kind in sorted(rule.schema_kinds)
    ],
)
def test_every_admitted_parameter_serialization_has_a_runtime_strategy(
    rule: object, kind: str
) -> None:
    schema, value = _schema_and_value(kind)
    parameter = OpenApiParameter(
        name="value&name",
        location=rule.location,
        required=rule.location == "path",
        description="",
        style=rule.style,
        explode=rule.explode,
        capability_schema=schema,
    )
    OpenApiValueValidator().validate(value, schema, "parameter")
    serializer = OpenApiParameterSerializer()

    if rule.location == "query":
        encoded = serializer.encode_query(serializer.query(parameter, value))
        assert "&name" not in encoded
        assert "c=d" not in encoded
    else:
        assert serializer.simple(parameter, value)


def test_primitive_enum_rejects_value_outside_declared_values() -> None:
    schema = PrimitiveSchema(
        type="string",
        format="",
        description="Workflow status.",
        enum=("todo", "done"),
    )

    with pytest.raises(ValueError, match="Schema validation failed at parameter"):
        OpenApiValueValidator().validate("blocked", schema, "parameter")


def test_nested_parameter_values_are_not_admitted_to_scalar_strategies() -> None:
    primitive = _primitive()
    nested = ObjectSchema(
        properties={"nested": ArraySchema(items=primitive, description="")},
        required=("nested",),
        description="",
    )
    parameter = OpenApiParameter(
        name="filter",
        location="query",
        required=False,
        description="",
        style="deepObject",
        explode=True,
        capability_schema=nested,
    )

    with pytest.raises(ValueError, match="unsupported parameter serialization"):
        OpenApiParameterSerializer().query(parameter, {"nested": ["unsafe"]})
