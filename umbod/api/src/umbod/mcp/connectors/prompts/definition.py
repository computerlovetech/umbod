from collections.abc import Callable, Mapping
from inspect import Signature, signature
from typing import Annotated, Any, Protocol, get_args, get_origin

from fastmcp import FastMCP
from pydantic import Field
from pydantic.fields import FieldInfo

from umbod.core.connectors.native.runtime import ConnectorPromptMapping

from umbod.mcp.connectors.prompts.naming import prompt_name


class ConnectorPromptRegistrar(Protocol):
    def register(
        self,
        mcp: FastMCP,
        mapping: ConnectorPromptMapping,
    ) -> None: ...


class FastMcpConnectorPromptRegistrar:
    def register(
        self,
        mcp: FastMCP,
        mapping: ConnectorPromptMapping,
    ) -> None:
        def connector_prompt(**arguments: Any) -> Any:
            return mapping.operation(**arguments)

        connector_prompt.__signature__ = connector_prompt_signature(mapping.operation)
        connector_prompt.__annotations__ = connector_prompt_annotations(
            mapping.operation, getattr(mapping, "parameters", {})
        )
        mcp.prompt(
            name=prompt_name(mapping),
            description=getattr(mapping, "description", None),
            meta={
                "connector_id": mapping.connector_id,
                "capability_kind": "prompt",
                "capability_key": mapping.name,
                "operation_name": mapping.name,
            },
        )(connector_prompt)


def connector_prompt_signature(operation: Callable[..., object]) -> Signature:
    operation_signature = signature(operation)
    return Signature(
        parameters=[
            parameter.replace(default=Signature.empty)
            if isinstance(parameter.default, FieldInfo)
            else parameter
            for parameter in operation_signature.parameters.values()
        ],
        return_annotation=operation_signature.return_annotation,
    )


def connector_prompt_annotations(
    operation: Callable[..., object],
    parameters: Mapping[str, Any],
) -> dict[str, object]:
    operation_signature = signature(operation)
    parameter_descriptions = _parameter_descriptions(parameters)
    annotations: dict[str, object] = {}
    for name, parameter in operation_signature.parameters.items():
        annotation = (
            Any if parameter.annotation is Signature.empty else parameter.annotation
        )
        description = parameter_descriptions.get(name)
        annotations[name] = (
            annotation
            if description is None
            else _described_annotation(annotation, description)
        )
    if operation_signature.return_annotation is not Signature.empty:
        annotations["return"] = operation_signature.return_annotation
    return annotations


def _parameter_descriptions(parameters: Mapping[str, Any]) -> dict[str, str]:
    properties = parameters.get("properties", {})
    if not isinstance(properties, Mapping):
        return {}
    return {
        str(name): str(schema["description"])
        for name, schema in properties.items()
        if isinstance(schema, Mapping) and isinstance(schema.get("description"), str)
    }


def _described_annotation(annotation: object, description: str) -> object:
    if get_origin(annotation) is Annotated:
        args = get_args(annotation)
        if not args:
            return annotation
        return Annotated[args[0], *args[1:], Field(description=description)]
    return Annotated[annotation, Field(description=description)]
