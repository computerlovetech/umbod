from umbod.core.capabilities.tools.output_schema import AbsentConnectorToolOutputSchema, ConnectorToolOutputSchema, PresentConnectorToolOutputSchema
from umbod.core.connectors.openapi.models import OpenApiEndpointCapability, OpenApiSchema


def openapi_json_schema(schema: OpenApiSchema) -> dict[str, object]:
    if schema.type in {"string", "integer", "number", "boolean"}:
        result: dict[str, object] = {"type": schema.type}
        if schema.format:
            result["format"] = schema.format
    elif schema.type == "array":
        result = {"type": "array", "items": openapi_json_schema(schema.items)}
    elif schema.type == "object":
        result = {
            "type": "object",
            "properties": {
                name: openapi_json_schema(property_schema)
                for name, property_schema in schema.properties.items()
            },
            "required": list(schema.required),
            "additionalProperties": schema.additional_properties
            if isinstance(schema.additional_properties, bool)
            else openapi_json_schema(schema.additional_properties),
        }
    elif schema.type == "null":
        result = {"type": "null"}
    elif schema.type == "composition":
        result = {schema.operator: [openapi_json_schema(member) for member in schema.schemas]}
    elif schema.type == "boolean_schema":
        result = {} if schema.allows_values else {"not": {}}
    else:
        result = {}
    return _schema_metadata(result, schema)


def _schema_metadata(
    result: dict[str, object], schema: OpenApiSchema
) -> dict[str, object]:
    if schema.description:
        result["description"] = schema.description
    enum_values = getattr(schema, "enum", ())
    if enum_values:
        result["enum"] = list(enum_values)
    return result


def openapi_output_schema(
    capability: OpenApiEndpointCapability,
) -> ConnectorToolOutputSchema:
    numeric_successes = sorted(
        (
            response
            for response in capability.response_bodies
            if response.status_code.isdigit() and 200 <= int(response.status_code) <= 299
        ),
        key=lambda response: (
            int(response.status_code),
            response.media_type != "application/json",
            response.media_type,
        ),
    )
    default_responses = sorted(
        (response for response in capability.response_bodies if response.status_code == "default"),
        key=lambda response: (
            response.media_type != "application/json",
            response.media_type,
        ),
    )
    candidates = [*numeric_successes, *default_responses]
    if not candidates:
        return AbsentConnectorToolOutputSchema()
    return PresentConnectorToolOutputSchema(
        output_schema=openapi_json_schema(candidates[0].capability_schema)
    )


def openapi_execution_schema(
    connector_id: str, capability: OpenApiEndpointCapability
) -> dict[str, object]:
    locations = {
        location: _location_schema(capability, location)
        for location in ("path", "query", "header")
    }
    return {
        "type": "object",
        "properties": {
            "connector_id": {"type": "string", "const": connector_id},
            "operation_id": {"type": "string", "const": capability.operation_id},
            "path": locations["path"],
            "query": locations["query"],
            "headers": locations["header"],
            "body": _body_schema(capability),
        },
        "required": [
            "connector_id", "operation_id", "path", "query", "headers", "body"
        ],
    }


def _location_schema(
    capability: OpenApiEndpointCapability, location: str
) -> dict[str, object]:
    parameters = tuple(
        parameter for parameter in capability.parameters if parameter.location == location
    )
    return {
        "type": "object",
        "properties": {
            parameter.name: openapi_json_schema(parameter.capability_schema)
            for parameter in parameters
        },
        "required": [parameter.name for parameter in parameters if parameter.required],
        "additionalProperties": False,
    }


def _body_schema(capability: OpenApiEndpointCapability) -> dict[str, object]:
    value_schema = (
        openapi_json_schema(capability.request_bodies[0].capability_schema)
        if capability.request_bodies
        else {}
    )
    return {
        "description": "Tagged JSON body. Use state 'missing' or state 'present' with value.",
        "oneOf": [
            {
                "type": "object",
                "properties": {"state": {"const": "missing"}},
                "required": ["state"],
            },
            {
                "type": "object",
                "properties": {
                    "state": {"const": "present"},
                    "value": value_schema,
                },
                "required": ["state", "value"],
            },
        ],
    }


def openapi_parameters_schema(capability: OpenApiEndpointCapability) -> dict[str, object]:
    properties: dict[str, object] = {}
    required: list[str] = []
    for parameter in capability.parameters:
        parameter_schema = openapi_json_schema(parameter.capability_schema)
        if parameter.description:
            parameter_schema["description"] = parameter.description
        properties[parameter.name] = parameter_schema
        if parameter.required and parameter.name not in required:
            required.append(parameter.name)
    if capability.request_bodies:
        request_body = capability.request_bodies[0]
        body_name = "requestBody" if "body" in properties else "body"
        body_schema = openapi_json_schema(request_body.capability_schema)
        if request_body.description:
            body_schema["description"] = request_body.description
        properties[body_name] = body_schema
        if request_body.required:
            required.append(body_name)
    return {"type": "object", "properties": properties, "required": required}
