from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Generic, TypeVar

from umbod_sdk.connectors.capability_description import CapabilityDescription
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
    if not description:
        raise ValueError("tool requires a description")
    unknown_options = set(options) - {"name", "parameters", "output_schema"}
    if unknown_options:
        option = sorted(unknown_options)[0]
        raise TypeError(f"tool() got an unexpected keyword argument '{option}'")
    output_schema = (
        PresentConnectorToolOutputSchema(options["output_schema"])
        if "output_schema" in options
        else AbsentConnectorToolOutputSchema()
    )
    if isinstance(output_schema, PresentConnectorToolOutputSchema) and not isinstance(
        output_schema.output_schema, dict
    ):
        raise TypeError("tool output_schema must be a JSON Schema object")

    def decorate(function: ConnectorToolOperation) -> ConnectorToolOperation:
        definition.tools.append(
            ToolDefinition(
                operation_name=options.get("name") or function.__name__,
                function=function,
                description=description,
                parameters=options.get("parameters") or {},
                output_schema=output_schema,
            )
        )
        return function

    return decorate


def prompt_decorator(
    definition: ConnectorDefinition,
    *,
    options: Mapping[str, Any],
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
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
