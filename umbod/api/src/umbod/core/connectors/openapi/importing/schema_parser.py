from collections.abc import Callable, Mapping
from typing import Any, cast

from umbod.core.connectors.openapi.importing.json_pointer import JsonPointerResolutionError
from umbod.core.connectors.openapi.models import (
    ArraySchema,
    BooleanSchema,
    CompositionSchema,
    NullSchema,
    ObjectSchema,
    OpenApiSchema,
    PrimitiveSchema,
    UnspecifiedSchema,
)
from umbod.core.connectors.openapi.importing.parsing import Location, ValidationIssues

ReferenceResolver = Callable[[str], object]


class OpenApiSchemaParser:
    def __init__(self, issues: ValidationIssues, resolver: ReferenceResolver) -> None:
        self._issues = issues
        self._resolver = resolver
        self._active_references: set[str] = set()

    def parse(self, raw: object, location: Location) -> OpenApiSchema | None:
        if isinstance(raw, bool):
            return BooleanSchema(allows_values=raw)
        if raw is None:
            return UnspecifiedSchema(description="")
        if not isinstance(raw, Mapping):
            self._issues.add("invalid_schema", location, "Schema must be an object or boolean")
            return None
        if "$ref" in raw:
            return self._parse_reference(raw, location)
        description = raw.get("description", "")
        if not isinstance(description, str):
            self._issues.add(
                "invalid_schema", (*location, "description"), "Schema description must be a string"
            )
            return None
        composition = self._parse_composition(raw, location, description)
        if composition is not None:
            return composition
        schema_type = self._normalized_type(raw.get("type"), location)
        if schema_type is None:
            if "properties" in raw or "additionalProperties" in raw:
                schema_type = "object"
            else:
                return UnspecifiedSchema(description=description)
        if schema_type in ("string", "integer", "number", "boolean"):
            schema_format = raw.get("format", "")
            if not isinstance(schema_format, str):
                self._issues.add(
                    "invalid_schema", (*location, "format"), "Schema format must be a string"
                )
                return None
            raw_enum = raw.get("enum", [])
            if not isinstance(raw_enum, list) or ("enum" in raw and not raw_enum):
                self._issues.add(
                    "invalid_schema", (*location, "enum"), "Schema enum must be a non-empty array"
                )
                return None
            return PrimitiveSchema(
                type=cast(Any, schema_type),
                format=schema_format,
                description=description,
                enum=tuple(raw_enum),
            )
        if schema_type == "null":
            return NullSchema(description=description)
        if schema_type == "array":
            items = self.parse(raw.get("items"), (*location, "items"))
            return ArraySchema(items=items, description=description) if items is not None else None
        if schema_type == "object":
            return self._parse_object(raw, location, description)
        self._issues.add("unsupported_schema", (*location, "type"), "Schema type is unsupported")
        return None

    def _parse_reference(
        self, raw: Mapping[object, object], location: Location
    ) -> OpenApiSchema | None:
        reference = raw.get("$ref")
        if not isinstance(reference, str):
            self._issues.add("invalid_reference", (*location, "$ref"), "Reference must be a string")
            return None
        if reference in self._active_references:
            return UnspecifiedSchema(description="Recursive schema reference")
        try:
            self._active_references.add(reference)
            resolved = self._resolver(reference)
            if len(raw) > 1 and isinstance(resolved, Mapping):
                resolved = {
                    **resolved,
                    **{key: value for key, value in raw.items() if key != "$ref"},
                }
            return self.parse(resolved, location)
        except JsonPointerResolutionError as error:
            self._issues.add("unsupported_reference", (*location, "$ref"), str(error))
            return None
        finally:
            self._active_references.discard(reference)

    def _parse_composition(
        self, raw: Mapping[object, object], location: Location, description: str
    ) -> OpenApiSchema | None:
        for operator in ("oneOf", "anyOf", "allOf"):
            if operator not in raw:
                continue
            values = raw[operator]
            if not isinstance(values, list) or not values:
                self._issues.add(
                    "invalid_schema", (*location, operator), "Composition must be a non-empty array"
                )
                return None
            schemas = tuple(
                filter(
                    None,
                    (
                        self.parse(value, (*location, operator, index))
                        for index, value in enumerate(values)
                    ),
                )
            )
            return CompositionSchema(
                operator=cast(Any, operator), schemas=schemas, description=description
            )
        if "not" in raw:
            parsed = self.parse(raw["not"], (*location, "not"))
            return (
                CompositionSchema(operator="not", schemas=(parsed,), description=description)
                if parsed is not None
                else None
            )
        return None

    def _normalized_type(self, raw_type: object, location: Location) -> str | None:
        if raw_type is None:
            return None
        if isinstance(raw_type, str):
            return raw_type
        if (
            isinstance(raw_type, list)
            and raw_type
            and all(isinstance(value, str) for value in raw_type)
        ):
            non_null = [value for value in raw_type if value != "null"]
            if len(non_null) == 1:
                return non_null[0]
            if not non_null:
                return "null"
            return None
        self._issues.add(
            "invalid_schema", (*location, "type"), "Schema type must be a string or string array"
        )
        return None

    def _parse_object(
        self, raw: Mapping[object, object], location: Location, description: str
    ) -> OpenApiSchema | None:
        raw_properties = raw.get("properties", {})
        raw_required = raw.get("required", [])
        if (
            not isinstance(raw_properties, Mapping)
            or not isinstance(raw_required, list)
            or not all(isinstance(item, str) for item in raw_required)
        ):
            self._issues.add("invalid_schema", location, "Object schema attributes are invalid")
            return None
        properties: dict[str, OpenApiSchema] = {}
        for name, value in raw_properties.items():
            if not isinstance(name, str):
                self._issues.add(
                    "invalid_schema", (*location, "properties"), "Property names must be strings"
                )
                continue
            parsed = self.parse(value, (*location, "properties", name))
            if parsed is not None:
                properties[name] = parsed
        additional = raw.get("additionalProperties", True)
        if isinstance(additional, Mapping) or isinstance(additional, bool):
            parsed_additional = (
                self.parse(additional, (*location, "additionalProperties"))
                if isinstance(additional, Mapping)
                else additional
            )
        else:
            parsed_additional = True
        return ObjectSchema(
            properties=properties,
            required=tuple(raw_required),
            description=description,
            additional_properties=parsed_additional,
        )
