from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from umbod.core.capabilities.tools.output_schema import AbsentConnectorToolOutputSchema, ConnectorToolOutputSchema, PresentConnectorToolOutputSchema
from umbod.core.connectors.native.tools.descriptions import ConnectorToolDescriptionState, ConnectorToolParameterDescription


ConnectorToolResult = Mapping[str, Any] | Awaitable[Mapping[str, Any]]
ConnectorToolOperation = Callable[..., ConnectorToolResult]
ConnectorToolParameters = Mapping[str, Any] | Sequence[ConnectorToolParameterDescription]


class ConnectorToolMapping(Protocol):
    connector_id: str
    tool_name_prefix: str
    operation_name: str
    description: str
    operation: ConnectorToolOperation
    parameters: ConnectorToolParameters
    output_schema: ConnectorToolOutputSchema


@dataclass(frozen=True)
class ConcreteConnectorToolMapping:
    connector_id: str
    operation_name: str
    description: str
    operation: ConnectorToolOperation
    parameters: ConnectorToolParameters
    output_schema: ConnectorToolOutputSchema = AbsentConnectorToolOutputSchema()
    tool_name_prefix: str = ""


def tool_mappings_from_handlers(
    connector_id: str,
    descriptions: Mapping[str, ConnectorToolDescriptionState],
    handlers: Mapping[str, ConnectorToolOperation],
    tool_name_prefix: str,
) -> list[ConcreteConnectorToolMapping]:
    return [
        ConcreteConnectorToolMapping(
            connector_id=connector_id,
            tool_name_prefix=tool_name_prefix,
            operation_name=operation_name,
            description=descriptions[operation_name].description,
            operation=handler,
            parameters=descriptions[operation_name].parameters,
            output_schema=(
                PresentConnectorToolOutputSchema(descriptions[operation_name].output_schema)
                if hasattr(descriptions[operation_name], "output_schema")
                else AbsentConnectorToolOutputSchema()
            ),
        )
        for operation_name, handler in handlers.items()
    ]


__all__ = [
    "ConcreteConnectorToolMapping",
    "ConnectorToolMapping",
    "ConnectorToolOperation",
    "ConnectorToolParameters",
    "ConnectorToolResult",
    "tool_mappings_from_handlers",
]
