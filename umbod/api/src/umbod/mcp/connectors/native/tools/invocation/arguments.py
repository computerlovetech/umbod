from collections.abc import Callable, Mapping
from inspect import Signature, signature
from types import UnionType
from typing import Annotated, Any, Union, get_args, get_origin


def resolve_connector_tool_arguments(
    operation: Callable[..., object], arguments: Mapping[str, Any]
) -> dict[str, Any]:
    resolved_arguments = dict(arguments)
    for name, parameter in signature(operation).parameters.items():
        if name not in resolved_arguments and _is_nullable_annotation(parameter.annotation):
            resolved_arguments[name] = None
    return resolved_arguments


def _is_nullable_annotation(annotation: object) -> bool:
    if annotation is Signature.empty:
        return False
    if get_origin(annotation) is Annotated:
        annotation = get_args(annotation)[0]
    origin = get_origin(annotation)
    if origin is Union or origin is UnionType:
        return type(None) in get_args(annotation)
    return False
