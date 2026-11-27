from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from functools import partial
from pathlib import Path
from typing import Any, Generic, TypeVar

from umbod_sdk.connectors.capability_description import CapabilityDescription
from umbod_sdk.connectors.declaration import tool_decorator as declaration_tool_decorator
from umbod_sdk.connectors.output_schema import (
    AbsentConnectorToolOutputSchema,
    ConnectorToolOutputSchema,
    PresentConnectorToolOutputSchema,
)
from umbod_sdk.connectors.proxies import Model
from umbod_sdk.connectors.models import ConnectorConfigurationCheckResult

ConnectorToolOperation = Callable[..., Any]
ConnectorConfigurationCheck = Callable[..., bool | ConnectorConfigurationCheckResult]
ConnectorValue = TypeVar("ConnectorValue")


@dataclass(frozen=True)
class AbsentConnectorValue:
    pass


@dataclass(frozen=True)
class PresentConnectorValue(Generic[ConnectorValue]):
    value: ConnectorValue


ConnectorIcon = AbsentConnectorValue | PresentConnectorValue[Path]
ConnectorExtension = AbsentConnectorValue | PresentConnectorValue[Mapping[str, object]]
ConnectorConfigurationCheckState = (
    AbsentConnectorValue | PresentConnectorValue[ConnectorConfigurationCheck]
)


@dataclass(frozen=True)
class ToolDefinition:
    operation_name: str
    function: ConnectorToolOperation
    description: str
    parameters: Mapping[str, str]
    output_schema: ConnectorToolOutputSchema = field(
        default_factory=AbsentConnectorToolOutputSchema
    )
    input_schema: AbsentConnectorValue | PresentConnectorValue[dict[str, Any]] = field(
        default_factory=AbsentConnectorValue
    )


@dataclass(frozen=True)
class PromptDefinition:
    name: str
    function: Callable[..., Any]
    description: str
    parameters: Mapping[str, str]


@dataclass(frozen=True)
class ResourceDefinition:
    uri_template: str
    name: str
    function: Callable[..., Any]
    description: str
    parameters: Mapping[str, str]


@dataclass
class ConnectorDefinition:
    id: str
    name: str
    description: str
    capability_description: CapabilityDescription
    configuration: type[Model]
    icon: ConnectorIcon = field(default_factory=AbsentConnectorValue)
    extension: ConnectorExtension = field(default_factory=AbsentConnectorValue)
    configuration_check: ConnectorConfigurationCheckState = field(
        default_factory=AbsentConnectorValue
    )
    tools: list[ToolDefinition] = field(default_factory=list)
    prompts: list[PromptDefinition] = field(default_factory=list)
    resources: list[ResourceDefinition] = field(default_factory=list)


def tool_decorator(
    definition: ConnectorDefinition,
    *,
    description: str,
    options: Mapping[str, Any],
) -> Callable[[ConnectorToolOperation], ConnectorToolOperation]:
    return declaration_tool_decorator(
        partial(_register_tool, definition), description=description, options=dict(options)
    )


def _register_tool(
    definition: ConnectorDefinition,
    description: str,
    options: Mapping[str, Any],
    function: ConnectorToolOperation,
) -> None:
    definition.tools.append(
        ToolDefinition(
            operation_name=options.get("name") or function.__name__,
            function=function,
            description=description,
            parameters=options.get("parameters") or {},
            output_schema=(
                PresentConnectorToolOutputSchema(options["output_schema"])
                if "output_schema" in options
                else AbsentConnectorToolOutputSchema()
            ),
            input_schema=(
                PresentConnectorValue(options["input_schema"])
                if "input_schema" in options
                else AbsentConnectorValue()
            ),
        )
    )


def prompt_decorator(
    definition: ConnectorDefinition,
    *,
    options: Mapping[str, Any],
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    unknown_options = set(options) - {"name", "description", "parameters"}
    if unknown_options:
        option = sorted(unknown_options)[0]
        raise TypeError(f"prompt() got an unexpected keyword argument '{option}'")

    def decorate(function: Callable[..., Any]) -> Callable[..., Any]:
        definition.prompts.append(
            PromptDefinition(
                name=options.get("name") or function.__name__,
                function=function,
                description=options.get("description") or "",
                parameters=options.get("parameters") or {},
            )
        )
        return function

    return decorate


def resource_decorator(
    definition: ConnectorDefinition,
    uri_template: str,
    *,
    options: Mapping[str, Any],
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    unknown_options = set(options) - {"name", "description", "parameters"}
    if unknown_options:
        option = sorted(unknown_options)[0]
        raise TypeError(f"resource() got an unexpected keyword argument '{option}'")

    def decorate(function: Callable[..., Any]) -> Callable[..., Any]:
        definition.resources.append(
            ResourceDefinition(
                uri_template=uri_template,
                name=options.get("name") or "",
                function=function,
                description=options.get("description") or "",
                parameters=options.get("parameters") or {},
            )
        )
        return function

    return decorate
