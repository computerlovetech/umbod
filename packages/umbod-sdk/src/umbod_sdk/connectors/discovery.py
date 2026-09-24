import os
from dataclasses import dataclass, field
from importlib.metadata import entry_points
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import ModuleType
from typing import Any, Literal, overload

from umbod_sdk.connectors.types import ConnectorPlugin

CONNECTOR_PLUGIN_ENTRY_POINT_GROUP = "umbod.connectors"
CONNECTOR_PLUGIN_DIR_ENVIRONMENT_VARIABLE = "UMBOD_CONNECTOR_PLUGIN_DIR"


@dataclass(frozen=True)
class ConnectorPluginDiagnostic:
    source: str
    message: str


@dataclass(frozen=True)
class ConnectorPluginDiscoveryResult:
    plugins: list[ConnectorPlugin]
    diagnostics: list[ConnectorPluginDiagnostic] = field(default_factory=list)


@overload
def load_connector_plugins(include_diagnostics: Literal[False]) -> list[ConnectorPlugin]: ...


@overload
def load_connector_plugins(
    include_diagnostics: Literal[True],
) -> ConnectorPluginDiscoveryResult: ...


@overload
def load_connector_plugins(
    include_diagnostics: bool,
) -> list[ConnectorPlugin] | ConnectorPluginDiscoveryResult: ...


def load_connector_plugins(
    include_diagnostics: bool,
) -> list[ConnectorPlugin] | ConnectorPluginDiscoveryResult:
    discovered_plugins: list[ConnectorPlugin] = []
    diagnostics: list[ConnectorPluginDiagnostic] = []
    discovered_plugins.extend(_entry_point_plugins(diagnostics))
    discovered_plugins.extend(_folder_plugins(_plugin_dir(), diagnostics))
    plugins = list(index_connector_plugins(discovered_plugins).values())
    if include_diagnostics:
        return ConnectorPluginDiscoveryResult(plugins=plugins, diagnostics=diagnostics)
    return plugins


def _entry_point_plugins(diagnostics: list[ConnectorPluginDiagnostic]) -> list[ConnectorPlugin]:
    plugins: list[ConnectorPlugin] = []
    for entry_point in entry_points(group=CONNECTOR_PLUGIN_ENTRY_POINT_GROUP):
        try:
            plugins.extend(_coerce_plugins(entry_point.load()))
        except Exception as error:
            diagnostics.append(
                ConnectorPluginDiagnostic(source=str(entry_point), message=str(error))
            )
    return plugins


def _folder_plugins(
    path: Path, diagnostics: list[ConnectorPluginDiagnostic]
) -> list[ConnectorPlugin]:
    if not path.exists():
        return []
    plugins: list[ConnectorPlugin] = []
    for plugin_file in sorted(path.glob("*.py")):
        if plugin_file.name.startswith("_"):
            continue
        try:
            plugins.extend(_plugins_from_module(_load_module(plugin_file)))
        except Exception as error:
            diagnostics.append(
                ConnectorPluginDiagnostic(source=str(plugin_file), message=str(error))
            )
    return plugins


def _plugin_dir() -> Path:
    configured_path = os.environ.get(CONNECTOR_PLUGIN_DIR_ENVIRONMENT_VARIABLE)
    if configured_path is not None and configured_path.strip():
        return Path(configured_path)
    return Path.cwd() / "plugins" / "connectors"


def _load_module(path: Path) -> ModuleType:
    module_name = f"umbod_connector_plugin_{path.stem}_{abs(hash(path))}"
    spec = spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ValueError(f"connector plugin file could not be loaded: {path}")
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _plugins_from_module(module: ModuleType) -> list[ConnectorPlugin]:
    plugin = getattr(module, "plugin", None)
    plugins = getattr(module, "plugins", None)
    if plugin is not None:
        return _coerce_plugins(plugin)
    if isinstance(plugins, list):
        return [
            coerced_plugin for candidate in plugins for coerced_plugin in _coerce_plugins(candidate)
        ]
    candidates = [value for value in module.__dict__.values() if _looks_like_plugin(value)]
    return candidates


def _coerce_plugins(value: Any) -> list[ConnectorPlugin]:
    if _looks_like_plugin(value):
        return [value]
    if callable(value):
        candidate = value()
        if _looks_like_plugin(candidate):
            return [candidate]
    return []


def _looks_like_plugin(value: Any) -> bool:
    return callable(getattr(value, "definition", None)) and callable(
        getattr(value, "registration", None)
    )


def index_connector_plugins(plugins: list[ConnectorPlugin]) -> dict[str, ConnectorPlugin]:
    plugins_by_id: dict[str, ConnectorPlugin] = {}
    for plugin in plugins:
        connector_id = str(plugin.registration()["id"])
        if connector_id in plugins_by_id:
            raise ValueError(f"duplicate connector id: {connector_id}")
        plugins_by_id[connector_id] = plugin
    return plugins_by_id


__all__ = [
    "CONNECTOR_PLUGIN_ENTRY_POINT_GROUP",
    "CONNECTOR_PLUGIN_DIR_ENVIRONMENT_VARIABLE",
    "ConnectorPluginDiagnostic",
    "ConnectorPluginDiscoveryResult",
    "load_connector_plugins",
]
