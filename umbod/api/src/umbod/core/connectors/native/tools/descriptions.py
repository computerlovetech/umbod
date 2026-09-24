import re
from typing import Annotated, Any, Literal, TypeAlias

from pydantic import ConfigDict, Field, StringConstraints, TypeAdapter
from umbod.proxies import Model

MCP_TOOL_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9_./-]{1,64}$")
McpToolOperationName = Annotated[str, StringConstraints(pattern=MCP_TOOL_NAME_PATTERN.pattern)]


class ConnectorToolParameterDescription(Model):
    model_config = ConfigDict(extra="forbid")

    name: str
    description: str
    type: Literal["string", "integer", "number", "boolean"] = "string"
    required: bool = True


class ConnectorToolDescriptionBase(Model):
    model_config = ConfigDict(extra="forbid")

    operation_name: McpToolOperationName
    description: str
    parameters: list[ConnectorToolParameterDescription] = Field(default_factory=list)

    @property
    def label(self) -> str:
        return self.operation_name.replace("_", " ").capitalize()


class ConnectorToolDescription(ConnectorToolDescriptionBase):
    output_schema_status: Literal["absent"] = "absent"


class ConnectorToolDescriptionWithOutputSchema(ConnectorToolDescriptionBase):
    output_schema_status: Literal["present"] = "present"
    output_schema: dict[str, Any]


ConnectorToolDescriptionState: TypeAlias = Annotated[
    ConnectorToolDescription | ConnectorToolDescriptionWithOutputSchema,
    Field(discriminator="output_schema_status"),
]
_connector_tool_description_adapter = TypeAdapter(ConnectorToolDescriptionState)


def connector_tool_descriptions_from_registration(
    registration: object,
) -> dict[str, ConnectorToolDescriptionState]:
    if not isinstance(registration, dict):
        return {}
    raw_descriptions = registration.get("tool_descriptions", [])
    if not isinstance(raw_descriptions, list):
        return {}
    descriptions = [
        _connector_tool_description_adapter.validate_python(
            _legacy_compatible_tool_description(_model_dump(description))
        )
        for description in raw_descriptions
    ]
    return {description.operation_name: description for description in descriptions}


def _legacy_compatible_tool_description(value: object) -> object:
    if isinstance(value, dict) and "output_schema_status" not in value:
        return {**value, "output_schema_status": "absent"}
    return value


def _model_dump(value: object) -> object:
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if isinstance(value, dict):
        return {key: _model_dump(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_model_dump(item) for item in value]
    return value


__all__ = [
    "ConnectorToolDescription",
    "ConnectorToolDescriptionWithOutputSchema",
    "ConnectorToolDescriptionState",
    "ConnectorToolParameterDescription",
    "MCP_TOOL_NAME_PATTERN",
    "McpToolOperationName",
    "connector_tool_descriptions_from_registration",
]
