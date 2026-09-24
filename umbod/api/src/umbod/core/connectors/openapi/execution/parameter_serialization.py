from dataclasses import dataclass
from typing import Literal, TypeAlias

from umbod.core.connectors.openapi.models import (
    ArraySchema,
    ObjectSchema,
    OpenApiParameter,
    OpenApiSchema,
    PrimitiveSchema,
)

ParameterLocation: TypeAlias = Literal["path", "query", "header"]
ParameterStyle: TypeAlias = Literal[
    "simple", "form", "spaceDelimited", "pipeDelimited", "deepObject"
]
SchemaKind: TypeAlias = Literal["primitive", "array", "object"]


@dataclass(frozen=True)
class ParameterSerializationRule:
    location: ParameterLocation
    style: ParameterStyle
    explode: bool
    schema_kinds: frozenset[SchemaKind]


ALL_SCHEMA_KINDS: frozenset[SchemaKind] = frozenset({"primitive", "array", "object"})
SUPPORTED_PARAMETER_SERIALIZATION: tuple[ParameterSerializationRule, ...] = (
    ParameterSerializationRule("path", "simple", False, ALL_SCHEMA_KINDS),
    ParameterSerializationRule("path", "simple", True, ALL_SCHEMA_KINDS),
    ParameterSerializationRule("query", "form", False, ALL_SCHEMA_KINDS),
    ParameterSerializationRule("query", "form", True, ALL_SCHEMA_KINDS),
    ParameterSerializationRule("query", "spaceDelimited", False, frozenset({"array"})),
    ParameterSerializationRule("query", "pipeDelimited", False, frozenset({"array"})),
    ParameterSerializationRule("query", "deepObject", True, frozenset({"object"})),
    ParameterSerializationRule("header", "simple", False, ALL_SCHEMA_KINDS),
    ParameterSerializationRule("header", "simple", True, ALL_SCHEMA_KINDS),
)

DEFAULT_PARAMETER_SERIALIZATION: dict[ParameterLocation, tuple[ParameterStyle, bool]] = {
    "path": ("simple", False),
    "query": ("form", True),
    "header": ("simple", False),
}


def schema_kind(schema: OpenApiSchema) -> SchemaKind | None:
    if isinstance(schema, PrimitiveSchema):
        return "primitive"
    if isinstance(schema, ArraySchema):
        return "array" if isinstance(schema.items, PrimitiveSchema) else None
    if isinstance(schema, ObjectSchema):
        return (
            "object"
            if all(isinstance(value, PrimitiveSchema) for value in schema.properties.values())
            else None
        )
    return None


class OpenApiParameterSerializationPolicy:
    def rejection_field(
        self,
        location: ParameterLocation,
        style: object,
        explode: object,
        allow_reserved: object,
        schema: OpenApiSchema,
    ) -> str | None:
        if allow_reserved is not False:
            return "allowReserved"
        location_rules = tuple(
            rule for rule in SUPPORTED_PARAMETER_SERIALIZATION if rule.location == location
        )
        if not isinstance(style, str) or not any(rule.style == style for rule in location_rules):
            return "style"
        style_rules = tuple(rule for rule in location_rules if rule.style == style)
        if not isinstance(explode, bool) or not any(
            rule.explode == explode for rule in style_rules
        ):
            return "explode"
        kind = schema_kind(schema)
        rule = next(rule for rule in style_rules if rule.explode == explode)
        if kind is None or kind not in rule.schema_kinds:
            return "schema"
        return None

    def supports(self, parameter: OpenApiParameter) -> bool:
        return (
            self.rejection_field(
                parameter.location,
                parameter.style,
                parameter.explode,
                False,
                parameter.capability_schema,
            )
            is None
        )
