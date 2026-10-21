from collections.abc import Callable, Mapping, Sequence
from inspect import Parameter, Signature, signature
from types import UnionType
from typing import Annotated, Any, Union, get_args, get_origin

from fastmcp.tools import ToolResult
from pydantic import Field

from umbod.core.connectors.native.tools.descriptions import ConnectorToolParameterDescription


def connector_tool_signature(operation: Callable[..., object]) -> Signature:
    operation_signature = signature(operation)
    return Signature(
        parameters=[
            _mcp_signature_parameter(parameter)
            for parameter in operation_signature.parameters.values()
        ],
        return_annotation=ToolResult,
    )


def connector_tool_annotations(
    operation: Callable[..., object],
    parameters: Sequence[ConnectorToolParameterDescription] | Mapping[str, Any],
) -> dict[str, object]:
    operation_signature = signature(operation)
    parameter_descriptions = _parameter_descriptions(parameters)
    annotations: dict[str, object] = {}
    for name, parameter in operation_signature.parameters.items():
        annotation = Any if parameter.annotation is Signature.empty else parameter.annotation
        annotations[name] = (
            _described_annotation(annotation, parameter_descriptions[name])
            if name in parameter_descriptions
            else annotation
        )
    annotations["return"] = ToolResult
    return annotations


def _is_nullable_annotation(annotation: object) -> bool:
    if annotation is Signature.empty:
        return False
    if get_origin(annotation) is Annotated:
        annotation = get_args(annotation)[0]
    origin = get_origin(annotation)
    if origin is Union or origin is UnionType:
        return type(None) in get_args(annotation)
    return False


def _mcp_signature_parameter(parameter: Parameter) -> Parameter:
    if _is_nullable_annotation(parameter.annotation):
        return parameter.replace(default=None)
    return parameter


def _parameter_descriptions(
    parameters: Sequence[ConnectorToolParameterDescription] | Mapping[str, Any],
) -> dict[str, str]:
    if isinstance(parameters, Mapping):
        properties = parameters.get("properties", {})
        if not isinstance(properties, Mapping):
            return {}
        return {
            str(name): str(schema["description"])
            for name, schema in properties.items()
            if isinstance(schema, Mapping) and isinstance(schema.get("description"), str)
        }
    return {parameter.name: parameter.description for parameter in parameters}


def _described_annotation(annotation: object, description: str) -> object:
    if get_origin(annotation) is Annotated:
        args = get_args(annotation)
        if not args:
            return annotation
        return Annotated[args[0], *args[1:], Field(description=description)]
    return Annotated[annotation, Field(description=description)]
