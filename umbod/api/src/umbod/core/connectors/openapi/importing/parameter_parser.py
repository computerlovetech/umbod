from collections.abc import Callable, Mapping
from typing import TypeAlias, cast

from umbod.core.connectors.openapi.errors import OpenApiValidationIssue
from umbod.core.connectors.openapi.models import OpenApiParameter, OpenApiSchema
from umbod.core.connectors.openapi.execution.parameter_serialization import (
    DEFAULT_PARAMETER_SERIALIZATION,
    OpenApiParameterSerializationPolicy,
    ParameterLocation,
    ParameterStyle,
)

Location: TypeAlias = tuple[str | int, ...]
SchemaParser: TypeAlias = Callable[
    [object, Location, list[OpenApiValidationIssue]], OpenApiSchema | None
]


class OpenApiParameterDefinitionParser:
    def __init__(self, parse_schema: SchemaParser) -> None:
        self._parse_schema = parse_schema
        self._policy = OpenApiParameterSerializationPolicy()

    def parse(
        self,
        raw_parameters: object,
        location: Location,
        issues: list[OpenApiValidationIssue],
    ) -> list[OpenApiParameter]:
        if not isinstance(raw_parameters, list):
            issues.append(
                self._issue("invalid_parameters", location, "Parameters must be an array")
            )
            return []
        parameters: list[OpenApiParameter] = []
        for index, raw_parameter in enumerate(raw_parameters):
            parsed = self._parse_one(raw_parameter, (*location, index), issues)
            if parsed is not None:
                parameters.append(parsed)
        return parameters

    def _parse_one(
        self,
        raw_parameter: object,
        location: Location,
        issues: list[OpenApiValidationIssue],
    ) -> OpenApiParameter | None:
        if not isinstance(raw_parameter, Mapping):
            issues.append(self._issue("invalid_parameter", location, "Parameter must be an object"))
            return None
        if "$ref" in raw_parameter:
            issues.append(
                self._issue(
                    "unsupported_reference", (*location, "$ref"), "References are unsupported"
                )
            )
            return None
        name = raw_parameter.get("name")
        raw_location = raw_parameter.get("in")
        required = raw_parameter.get("required", False)
        description = raw_parameter.get("description", "")
        if (
            not isinstance(name, str)
            or not name
            or raw_location not in DEFAULT_PARAMETER_SERIALIZATION
        ):
            issues.append(
                self._issue(
                    "invalid_parameter", location, "Parameter name and location are invalid"
                )
            )
            return None
        if not isinstance(required, bool) or not isinstance(description, str):
            issues.append(
                self._issue("invalid_parameter", location, "Parameter attributes are invalid")
            )
            return None
        if raw_location == "path" and required is not True:
            issues.append(
                self._issue(
                    "path_parameter_not_required",
                    (*location, "required"),
                    "Path parameters must be required",
                )
            )
            return None
        parameter_location = cast(ParameterLocation, raw_location)
        default_style, default_explode = DEFAULT_PARAMETER_SERIALIZATION[parameter_location]
        style = raw_parameter.get("style", default_style)
        explode = raw_parameter.get("explode", default_explode)
        schema = self._parse_schema(raw_parameter.get("schema"), (*location, "schema"), issues)
        if schema is None:
            return None
        rejection_field = self._policy.rejection_field(
            parameter_location,
            style,
            explode,
            raw_parameter.get("allowReserved", False),
            schema,
        )
        if rejection_field is not None:
            return None
        return OpenApiParameter(
            name=name,
            location=parameter_location,
            required=required,
            description=description,
            style=cast(ParameterStyle, style),
            explode=cast(bool, explode),
            capability_schema=schema,
        )

    def _issue(self, code: str, location: Location, message: str) -> OpenApiValidationIssue:
        return OpenApiValidationIssue(code=code, location=location, message=message)
