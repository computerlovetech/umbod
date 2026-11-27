from __future__ import annotations

from typing import Any, Callable


class Connector:
    def __init__(
        self,
        *,
        id: str,
        name: str,
        description: str,
        capability_description: str,
        configuration: object,
        **options: object,
    ) -> None:
        if set(options) - {"http_targets"}:
            raise TypeError("portable connectors do not support icon or extension options")
        self._explicit_configuration = isinstance(configuration, dict)
        self._http_targets = normalize_http_targets(options.get("http_targets", {}))
        if self._http_targets and not self._explicit_configuration:
            raise ValueError("http_targets require a portable connector with an explicit configuration schema")
        self._set_declaration_metadata({
            "id": id,
            "name": name,
            "description": description,
            "capability_description": capability_description,
            "configuration": configuration,
        })
        self._tool_manifests: dict[str, dict[str, object]] = {}
        self._handlers: dict[str, Callable[..., object]] = {}

    def _set_declaration_metadata(self, metadata: dict[str, Any]) -> None:
        self.id: str = metadata["id"]
        self.name: str = metadata["name"]
        self.description: str = metadata["description"]
        self.capability_description: str = metadata["capability_description"]
        self.configuration: object = metadata["configuration"]

    def _uses_explicit_configuration(self) -> bool:
        return self._explicit_configuration

    def configuration_check(self, function: Callable[..., Any]) -> Callable[..., Any]:
        self._register_configuration_check(function)
        return function

    def _register_configuration_check(self, function: Callable[..., Any]) -> None:
        self._handlers["configuration_check"] = function

    def tool(self, *, description: str, **options: object) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        return tool_decorator(self._register_tool, description=description, options=options)

    def _register_tool(
        self, description: str, options: dict[str, object], function: Callable[..., object]
    ) -> None:
        operation_name = options.get("name")
        if not isinstance(operation_name, str) or not operation_name.strip():
            raise ValueError("portable tools require an explicit name")
        if operation_name in self._tool_manifests:
            raise ValueError(f"connector '{self.id}' has duplicate tool operation name: {operation_name}")
        if "input_schema" not in options:
            raise ValueError(f"portable tool '{operation_name}' requires input_schema")
        if "parameters" in options:
            raise ValueError(f"portable tool '{operation_name}' declares parameter metadata in input_schema")
        handler_id = f"tool:{operation_name}"
        tool = {
            "operation_name": operation_name,
            "description": description,
            "handler_id": handler_id,
            "input_schema": options["input_schema"],
        }
        if "output_schema" in options:
            tool["output_schema"] = options["output_schema"]
        self._tool_manifests[operation_name] = tool
        self._handlers[handler_id] = function

    def manifest(self) -> dict[str, Any]:
        if not self._uses_explicit_configuration():
            raise ValueError("manifest() requires an explicit JSON Schema configuration")
        if "configuration_check" not in self._handlers:
            raise ValueError("connector requires a configuration check")
        if not self._tool_manifests:
            raise ValueError("portable connector requires at least one tool")
        manifest = {
            "manifest_version": 1,
            "connector_id": self.id,
            "display_name": self.name,
            "description": self.description,
            "capability_description": self.capability_description.strip(),
            "configuration_schema": self.configuration,
            "configuration_check_handler_id": "configuration_check",
            "tools": list(self._tool_manifests.values()),
        }
        if self._http_targets:
            manifest["manifest_version"] = 2
            manifest["http_targets"] = dict(self._http_targets)
        return manifest

    def _handler(self, handler_id: str) -> Callable[..., object]:
        return self._handlers[handler_id]


def normalize_http_targets(value: object) -> dict[str, str]:
    if not isinstance(value, dict) or len(value) > 16:
        raise ValueError("http_targets must be an object with at most 16 targets")
    targets: dict[str, str] = {}
    for target_id, description in value.items():
        if not is_http_target_id(target_id):
            raise ValueError("HTTP target ID must match [a-z][a-z0-9_]{0,63}")
        if not isinstance(description, str) or not description.strip() or len(description) > 256:
            raise ValueError("HTTP target description must be nonblank and at most 256 characters")
        targets[target_id] = description.strip()
    return targets


def is_http_target_id(value: object) -> bool:
    if not isinstance(value, str) or not 1 <= len(value) <= 64:
        return False
    letters = "abcdefghijklmnopqrstuvwxyz"
    allowed = letters + "0123456789_"
    return value[0] in letters and all(character in allowed for character in value)


def tool_decorator(
    register: Callable[[str, dict[str, object], Callable[..., Any]], None],
    *,
    description: str,
    options: dict[str, object],
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    if not description:
        raise ValueError("tool requires a description")
    unknown_options = set(options) - {"name", "parameters", "input_schema", "output_schema"}
    if unknown_options:
        option = sorted(unknown_options)[0]
        raise TypeError(f"tool() got an unexpected keyword argument '{option}'")
    for schema_key in ("input_schema", "output_schema"):
        if schema_key in options and not isinstance(options[schema_key], dict):
            raise TypeError(f"tool {schema_key} must be a JSON Schema object")

    def decorate(function: Callable[..., Any]) -> Callable[..., Any]:
        register(description, options, function)
        return function

    return decorate
