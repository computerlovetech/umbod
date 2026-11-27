from collections.abc import Iterator
from math import isfinite
from typing import Any
from urllib.parse import quote, unquote

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError
from jsonschema.validators import validator_for
from referencing import Registry
from referencing.exceptions import Unresolvable
from referencing.jsonschema import DRAFT202012, specification_with

from umbod_sdk.connectors.capability_description import validate_capability_description
from umbod_sdk.connectors.declaration import normalize_http_targets


def validate_manifest_schemas(manifest: dict[str, Any]) -> dict[str, Any]:
    checked = _copy_json_object(manifest, "manifest", set())
    reserved_parameters = _validate_manifest_version(checked)
    validate_capability_description(checked["capability_description"])
    _check_schema(checked["configuration_schema"], "configuration_schema")
    for tool in checked["tools"]:
        location = f"tool '{tool['operation_name']}'"
        _check_tool_input_schema(tool["input_schema"], f"{location} input_schema", reserved_parameters)
        if "output_schema" in tool:
            _check_schema(tool["output_schema"], f"{location} output_schema")
    return checked


def _validate_manifest_version(manifest: dict[str, Any]) -> tuple[str, ...]:
    version = manifest.get("manifest_version")
    if type(version) is not int:
        raise ValueError("manifest_version must be 1 or 2")
    if version == 1:
        if "http_targets" in manifest:
            raise ValueError("manifest version 1 cannot declare http_targets")
        return ("configuration",)
    if version == 2:
        targets = normalize_http_targets(manifest.get("http_targets", {}))
        if not targets:
            raise ValueError("manifest version 2 requires nonempty http_targets")
        manifest["http_targets"] = targets
        return ("configuration", "context")
    raise ValueError("manifest_version must be 1 or 2")


def validate_tool_input_schema(schema: dict[str, Any], operation_name: str) -> dict[str, Any]:
    location = f"tool '{operation_name}' input_schema"
    checked = _copy_json_object(schema, location, set())
    _check_tool_input_schema(checked, location, ("configuration",))
    return checked


def _check_tool_input_schema(
    schema: dict[str, Any], location: str, reserved_parameters: tuple[str, ...]
) -> None:
    _check_schema(schema, location)
    specification = specification_with(schema["$schema"], default=DRAFT202012) if "$schema" in schema else DRAFT202012
    root = specification.create_resource(schema)
    registry: Registry[Any] = Registry()
    pending = [(schema, registry.resolver_with_root(root))]
    seen: set[int] = set()
    while pending:
        current, resolver = pending.pop()
        if id(current) in seen:
            continue
        seen.add(id(current))
        for name in reserved_parameters:
            if _declares_parameter(current, name):
                raise ValueError(f"{location} cannot declare the reserved '{name}' parameter")
        pending.extend(
            (child, resolver.in_subresource(specification.create_resource(child)))
            for child in _argument_subschemas(current)
        )
        for keyword in ("$ref", "$dynamicRef", "$recursiveRef"):
            if keyword in current:
                reference = _local_argument_reference(current[keyword], location)
                try:
                    resolved = resolver.lookup(reference)
                except Unresolvable:
                    raise ValueError(f"{location} has an unresolved argument schema reference: {reference}") from None
                if not isinstance(resolved.contents, (dict, bool)):
                    raise ValueError(f"{location} argument schema reference must resolve to a JSON Schema: {reference}")
                if isinstance(resolved.contents, dict):
                    pending.append((resolved.contents, resolved.resolver))


def _declares_parameter(schema: dict[str, Any], name: str) -> bool:
    required = schema.get("required", [])
    if name in _schema_mapping(schema, "properties") or (isinstance(required, list) and name in required):
        return True
    for keyword in ("dependentRequired", "dependencies"):
        for property_name, dependency in _schema_mapping(schema, keyword).items():
            if isinstance(dependency, list) and (property_name == name or name in dependency):
                return True
    return False


def _argument_subschemas(schema: dict[str, Any]) -> Iterator[dict[str, Any]]:
    for keyword in ("allOf", "anyOf", "oneOf", "extends"):
        value = schema.get(keyword, [])
        if isinstance(value, list):
            yield from (item for item in value if isinstance(item, dict))
        elif isinstance(value, dict):
            yield value
    for keyword in ("if", "then", "else"):
        if keyword in schema and isinstance(schema[keyword], dict):
            yield schema[keyword]
    for keyword in ("dependentSchemas", "dependencies"):
        yield from (item for item in _schema_mapping(schema, keyword).values() if isinstance(item, dict))


def _schema_mapping(schema: dict[str, Any], keyword: str) -> dict[str, Any]:
    value = schema.get(keyword)
    return value if isinstance(value, dict) else {}


def _local_argument_reference(reference: object, location: str) -> str:
    if reference == "#":
        return "#"
    fragment = unquote(reference[1:]) if isinstance(reference, str) and reference.startswith("#") else ""
    if not fragment.startswith("/"):
        raise ValueError(f"{location} requires a local JSON Pointer for argument schema references")
    return "#" + quote(fragment, safe="/~")


def _check_schema(schema: dict[str, Any], location: str) -> None:
    if not isinstance(schema, dict):
        raise ValueError(f"{location} must be a JSON Schema object")
    if "$schema" in schema and not isinstance(schema["$schema"], str):
        raise SchemaError(f"{location}: $schema must be a string")
    validator = validator_for(schema, default=None) if "$schema" in schema else Draft202012Validator
    if validator is None:
        raise SchemaError(f"{location} declares an unsupported JSON Schema dialect")
    try:
        validator.check_schema(schema)
    except SchemaError as error:
        raise SchemaError(f"{location}: {error.message}") from error


def _copy_json_value(value: object, location: str, ancestors: set[int]) -> Any:
    if value is None or type(value) in (str, bool, int):
        return value
    if type(value) is float and isfinite(value):
        return value
    if id(value) in ancestors:
        raise ValueError(f"{location} contains a circular JSON value")
    if isinstance(value, (dict, list)):
        ancestors.add(id(value))
        try:
            if isinstance(value, dict):
                return _copy_json_object(value, location, ancestors)
            return [
                _copy_json_value(item, f"{location}[{index}]", ancestors)
                for index, item in enumerate(value)
            ]
        finally:
            ancestors.remove(id(value))
    raise ValueError(f"{location} contains a non-JSON value")


def _copy_json_object(value: dict[Any, Any], location: str, ancestors: set[int]) -> dict[str, Any]:
    copied: dict[str, Any] = {}
    for key, item in value.items():
        if type(key) is not str:
            raise ValueError(f"{location} contains a non-string JSON object key")
        copied[key] = _copy_json_value(item, f"{location}.{key}", ancestors)
    return copied
