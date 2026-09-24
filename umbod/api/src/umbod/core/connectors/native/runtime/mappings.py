from collections.abc import Callable, Sequence
from dataclasses import dataclass
from inspect import Parameter, isawaitable, signature
from typing import Any

from pydantic.fields import FieldInfo

from umbod_sdk.connectors.api.definition import ConnectorDefinition, ToolDefinition
from umbod_sdk.connectors.api.parameters import (
    HIDDEN_PARAMETER_NAMES,
    prompt_parameters_schema,
    resource_parameters_schema,
    tool_parameters_schema,
)
from umbod_sdk.connectors.api.registration import validate_connector
from umbod.core.configuration import ConnectorCurrentConfigurationStore
from umbod.core.connectors.native.runtime.tools import (
    ConcreteConnectorToolMapping,
    ConnectorToolMapping,
    ConnectorToolOperation,
    ConnectorToolResult,
)


@dataclass(frozen=True)
class _OperationContext:
    definition: ConnectorDefinition
    tool: ToolDefinition
    configuration_store: ConnectorCurrentConfigurationStore


@dataclass(frozen=True)
class ConnectorPromptMapping:
    connector_id: str
    name: str
    description: str
    operation: Callable[..., Any]
    parameters: dict[str, Any]


@dataclass(frozen=True)
class ConnectorResourceMapping:
    connector_id: str
    uri_template: str
    name: str
    description: str
    read_operation: Callable[..., Any]
    parameters: dict[str, Any]

    def matches(self, uri: str) -> bool:
        template_parts = self.uri_template.split("/")
        uri_parts = uri.split("/")
        if len(template_parts) != len(uri_parts):
            return False
        return all(
            _resource_part_matches(template_part, uri_part)
            for template_part, uri_part in zip(template_parts, uri_parts, strict=True)
        )

    def read(self, uri: str) -> Any:
        return self.read_operation(**_resource_arguments(self.uri_template, uri))


@dataclass(frozen=True)
class _CapabilityOperationContext:
    definition: ConnectorDefinition
    function: Callable[..., Any]
    configuration_store: ConnectorCurrentConfigurationStore


def connector_tool_mappings(
    definition: ConnectorDefinition,
    *,
    tool_name_prefix: str,
    configuration_store: ConnectorCurrentConfigurationStore,
) -> Sequence[ConnectorToolMapping]:
    validate_connector(definition)
    return [
        ConcreteConnectorToolMapping(
            connector_id=definition.id,
            tool_name_prefix=tool_name_prefix,
            operation_name=tool.operation_name,
            description=tool.description,
            operation=_operation(
                _OperationContext(
                    definition=definition,
                    tool=tool,
                    configuration_store=configuration_store,
                )
            ),
            parameters=tool_parameters_schema(tool),
            output_schema=tool.output_schema,
        )
        for tool in definition.tools
    ]


def connector_prompt_mappings(
    definition: ConnectorDefinition,
    *,
    configuration_store: ConnectorCurrentConfigurationStore,
) -> Sequence[ConnectorPromptMapping]:
    validate_connector(definition)
    return [
        ConnectorPromptMapping(
            connector_id=definition.id,
            name=prompt.name,
            description=prompt.description,
            operation=_capability_operation(
                _CapabilityOperationContext(
                    definition=definition,
                    function=prompt.function,
                    configuration_store=configuration_store,
                )
            ),
            parameters=prompt_parameters_schema(prompt),
        )
        for prompt in definition.prompts
    ]


def connector_resource_mappings(
    definition: ConnectorDefinition,
    *,
    configuration_store: ConnectorCurrentConfigurationStore,
) -> Sequence[ConnectorResourceMapping]:
    validate_connector(definition)
    return [
        ConnectorResourceMapping(
            connector_id=definition.id,
            uri_template=resource.uri_template,
            name=resource.name,
            description=resource.description,
            read_operation=_capability_operation(
                _CapabilityOperationContext(
                    definition=definition,
                    function=resource.function,
                    configuration_store=configuration_store,
                )
            ),
            parameters=resource_parameters_schema(resource),
        )
        for resource in definition.resources
    ]


def _operation(context: _OperationContext) -> ConnectorToolOperation:
    clean_signature = _public_signature(context.tool.function)

    async def operation(*args: Any, **kwargs: Any) -> ConnectorToolResult:
        await _inject_hidden_parameters(context, kwargs)
        result = context.tool.function(*args, **kwargs)
        if isawaitable(result):
            return await result
        return result

    operation.__name__ = getattr(context.tool.function, "__name__", "connector_operation")
    operation.__annotations__ = {
        key: value
        for key, value in dict(getattr(context.tool.function, "__annotations__", {})).items()
        if key not in HIDDEN_PARAMETER_NAMES
    }
    operation.__signature__ = clean_signature
    return operation


def _capability_operation(context: _CapabilityOperationContext) -> Callable[..., Any]:
    clean_signature = _public_signature(context.function)

    async def operation(*args: Any, **kwargs: Any) -> Any:
        await _inject_capability_hidden_parameters(context, kwargs)
        result = context.function(*args, **kwargs)
        if isawaitable(result):
            return await result
        return result

    operation.__name__ = getattr(context.function, "__name__", "connector_capability")
    operation.__annotations__ = {
        key: value
        for key, value in dict(getattr(context.function, "__annotations__", {})).items()
        if key not in HIDDEN_PARAMETER_NAMES
    }
    operation.__signature__ = clean_signature
    return operation


def _public_signature(function: Callable[..., Any]) -> Any:
    return signature(function).replace(
        parameters=[
            parameter.replace(default=Parameter.empty)
            if isinstance(parameter.default, FieldInfo)
            else parameter
            for parameter in signature(function).parameters.values()
            if parameter.name not in HIDDEN_PARAMETER_NAMES
        ]
    )


async def _inject_hidden_parameters(context: _OperationContext, kwargs: dict[str, Any]) -> None:
    await _inject_capability_hidden_parameters(
        _CapabilityOperationContext(
            definition=context.definition,
            function=context.tool.function,
            configuration_store=context.configuration_store,
        ),
        kwargs,
    )


async def _inject_capability_hidden_parameters(
    context: _CapabilityOperationContext, kwargs: dict[str, Any]
) -> None:
    if "configuration" in signature(context.function).parameters:
        current_configuration = await context.configuration_store.get_current_configuration(
            context.definition.id
        )
        if current_configuration is None:
            raise RuntimeError(f"Connector {context.definition.id} is not configured")
        kwargs["configuration"] = context.definition.configuration.model_validate(
            current_configuration.model_dump()
        )


def _resource_part_matches(template_part: str, uri_part: str) -> bool:
    return (
        template_part.startswith("{") and template_part.endswith("}") or template_part == uri_part
    )


def _resource_arguments(uri_template: str, uri: str) -> dict[str, str]:
    return {
        template_part[1:-1]: uri_part
        for template_part, uri_part in zip(uri_template.split("/"), uri.split("/"), strict=True)
        if template_part.startswith("{") and template_part.endswith("}")
    }
