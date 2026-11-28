from json import dumps
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError
from jsonschema.validators import validator_for
from pydantic import JsonValue, TypeAdapter
from referencing import Registry
from referencing.exceptions import Unresolvable
from umbod_sdk.connectors.api.manifest import validate_manifest_schemas

from .contracts import PortableManifest, PortableTool
from .ports import PortableExecutionError

_MANIFEST = TypeAdapter(PortableManifest)
_JSON_VALUE = TypeAdapter(JsonValue)
_JSON_OBJECT = TypeAdapter(dict[str, JsonValue])
_MAX_DOCUMENT_BYTES = 2 * 1024 * 1024


def read_manifest(raw: object) -> PortableManifest:
    try:
        if not isinstance(raw, dict) or type(raw.get("manifest_version")) is not int:
            raise ValueError
        manifest = _MANIFEST.validate_python(raw, strict=True)
        json_snapshot(manifest)
        return _MANIFEST.validate_python(validate_manifest_schemas(manifest), strict=True)
    except (TypeError, ValueError, SchemaError, RecursionError):
        raise PortableExecutionError("Invalid portable connector manifest") from None


def check_manifest_handlers(manifest: PortableManifest) -> None:
    if manifest["configuration_check_handler_id"] != "configuration_check" or not manifest["tools"]:
        raise PortableExecutionError("Invalid portable connector handlers")
    operations: set[str] = set()
    for tool in manifest["tools"]:
        name = tool["operation_name"]
        if not name.strip() or name in operations or tool["handler_id"] != f"tool:{name}":
            raise PortableExecutionError("Invalid portable connector handlers")
        operations.add(name)


def tool_for(manifest: PortableManifest, operation: str) -> PortableTool:
    for tool in manifest["tools"]:
        if tool["operation_name"] == operation:
            return tool
    raise PortableExecutionError("Unknown portable connector operation")


def snapshot_object(value: object, failure: str) -> dict[str, JsonValue]:
    try:
        checked = _JSON_OBJECT.validate_python(value, strict=True)
        json_snapshot(checked)
    except (ValueError, RecursionError):
        raise PortableExecutionError(failure) from None
    return checked


def checked_result(value: object) -> JsonValue:
    try:
        checked = _JSON_VALUE.validate_python(value, strict=True)
        json_snapshot(checked)
    except (ValueError, RecursionError):
        raise PortableExecutionError("Invalid portable tool output") from None
    return checked


def enforce_schema(schema: dict[str, Any], value: JsonValue, failure: str) -> None:
    try:
        matches = validator_for(schema, default=Draft202012Validator)(schema, registry=Registry()).is_valid(value)
    except (Unresolvable, RecursionError):
        raise PortableExecutionError(failure) from None
    if not matches:
        raise PortableExecutionError(failure)


def json_snapshot(value: object) -> str:
    snapshot = dumps(value, allow_nan=False, sort_keys=True, separators=(",", ":"))
    if len(snapshot) > _MAX_DOCUMENT_BYTES:
        raise ValueError("Portable JSON document exceeds size limit")
    return snapshot
