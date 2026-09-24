from urllib.parse import quote

from pydantic import JsonValue

from umbod.core.connectors.openapi.models import (
    ArraySchema,
    OpenApiParameter,
    OpenApiSchema,
    PrimitiveSchema,
    UnspecifiedSchema,
)
from umbod.core.connectors.openapi.execution.parameter_serialization import (
    OpenApiParameterSerializationPolicy,
)


class OpenApiValueValidator:
    def validate(self, value: JsonValue, schema: OpenApiSchema, location: str) -> None:
        if isinstance(schema, UnspecifiedSchema):
            raise ValueError(f"Unsupported unspecified schema at {location}")
        if isinstance(schema, PrimitiveSchema):
            valid = (
                (schema.type == "string" and isinstance(value, str))
                or (schema.type == "boolean" and isinstance(value, bool))
                or (
                    schema.type == "integer"
                    and isinstance(value, int)
                    and not isinstance(value, bool)
                )
                or (
                    schema.type == "number"
                    and isinstance(value, (int, float))
                    and not isinstance(value, bool)
                )
            )
            if not valid or (schema.enum and value not in schema.enum):
                raise ValueError(f"Schema validation failed at {location}")
            return
        if isinstance(schema, ArraySchema):
            if not isinstance(value, list):
                raise ValueError(f"Schema validation failed at {location}")
            for index, item in enumerate(value):
                self.validate(item, schema.items, f"{location}[{index}]")
            return
        if not isinstance(value, dict):
            raise ValueError(f"Schema validation failed at {location}")
        if set(schema.required) - set(value):
            raise ValueError(f"Missing required object property at {location}")
        if set(value) - set(schema.properties):
            raise ValueError(f"Additional object property at {location}")
        for name, item in value.items():
            self.validate(item, schema.properties[name], f"{location}.{name}")


class OpenApiParameterSerializer:
    def __init__(self) -> None:
        self._policy = OpenApiParameterSerializationPolicy()

    def simple(self, parameter: OpenApiParameter, value: JsonValue) -> str:
        self._require_supported(parameter)
        if isinstance(value, list):
            return ",".join(self._scalar(item) for item in value)
        if isinstance(value, dict):
            values: list[str] = []
            for key in sorted(value):
                if parameter.explode:
                    values.append(f"{key}={self._scalar(value[key])}")
                else:
                    values.extend((key, self._scalar(value[key])))
            return ",".join(values)
        return self._scalar(value)

    def query(self, parameter: OpenApiParameter, value: JsonValue) -> list[tuple[str, str]]:
        self._require_supported(parameter)
        name = parameter.name
        if parameter.style == "deepObject":
            if not isinstance(value, dict):
                raise ValueError("deepObject requires an object")
            return [(f"{name}[{key}]", self._scalar(value[key])) for key in sorted(value)]
        if isinstance(value, list):
            if parameter.style == "form" and parameter.explode:
                return [(name, self._scalar(item)) for item in value]
            delimiter = {"form": ",", "spaceDelimited": " ", "pipeDelimited": "|"}[parameter.style]
            return [(name, delimiter.join(self._scalar(item) for item in value))]
        if isinstance(value, dict):
            if parameter.explode:
                return [(key, self._scalar(value[key])) for key in sorted(value)]
            return [(name, self.simple(parameter, value))]
        return [(name, self._scalar(value))]

    def encode_query(self, pairs: list[tuple[str, str]]) -> str:
        return "&".join(f"{quote(name, safe='')}={quote(value, safe='')}" for name, value in pairs)

    def _require_supported(self, parameter: OpenApiParameter) -> None:
        if not self._policy.supports(parameter):
            raise ValueError("Malformed operation contract: unsupported parameter serialization")

    def _scalar(self, value: JsonValue) -> str:
        if value is None or isinstance(value, (list, dict)):
            raise ValueError("Parameter value must match its serialization schema")
        if isinstance(value, bool):
            return "true" if value else "false"
        return str(value)
