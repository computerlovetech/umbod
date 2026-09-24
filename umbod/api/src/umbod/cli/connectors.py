import importlib
import sys
from importlib.metadata import distributions, entry_points, version
from inspect import Parameter, Signature
from pathlib import Path
from typing import Annotated, Any, NoReturn, Optional

import typer
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

from umbod_sdk.connectors.api.registration import validate_connector
from umbod_sdk.connectors.discovery import CONNECTOR_PLUGIN_ENTRY_POINT_GROUP
from umbod_sdk.connectors.types import ConnectorPlugin

app = typer.Typer(help="Connector plugin inspection commands.", no_args_is_help=True)


class ValidateCommand:
    __name__ = "validate"
    __signature__ = Signature(
        parameters=[
            Parameter(
                "plugin_path",
                Parameter.POSITIONAL_OR_KEYWORD,
                default=None,
                annotation=Annotated[
                    Optional[Path],
                    typer.Option(help="Python package directory containing connector plugins."),
                ],
            ),
        ],
        return_annotation=None,
    )

    def __call__(self, **kwargs: Any) -> None:
        try:
            plugin_path = kwargs.get("plugin_path")
            if plugin_path is not None:
                _add_plugin_path(Path(plugin_path))
            plugins = _load_and_validate_plugins()
        except typer.Exit:
            raise
        except Exception as error:
            _fail(f"Connector plugin validation failed: {error}")
        typer.echo(f"Connector plugins valid: {len(plugins)} loaded.")


def _add_plugin_path(plugin_path: Path) -> None:
    resolved_path = plugin_path.resolve(strict=True)
    if (resolved_path / "umbod_sdk").exists():
        raise ValueError("plugin bundle must not contain the connector SDK package")
    sdk_name = canonicalize_name("umbod")
    if any(
        canonicalize_name(distribution.metadata["Name"]) == sdk_name
        for distribution in distributions(path=[str(resolved_path)])
    ):
        raise ValueError("plugin bundle must not contain connector SDK metadata")
    sys.path.append(str(resolved_path))
    importlib.invalidate_caches()


def _load_and_validate_plugins() -> list[ConnectorPlugin]:
    sdk_name = canonicalize_name("umbod")
    sdk_version = version(sdk_name)
    plugins: list[ConnectorPlugin] = []
    connector_ids: set[str] = set()
    for entry_point in entry_points(group=CONNECTOR_PLUGIN_ENTRY_POINT_GROUP):
        _validate_sdk_requirement(entry_point.dist, sdk_name, sdk_version)
        plugin = _coerce_plugin(entry_point.load())
        if plugin is None:
            raise ValueError(f"entry point did not provide a connector plugin: {entry_point}")
        definition = plugin.definition()
        validate_connector(definition)
        if definition.id in connector_ids:
            raise ValueError(f"duplicate connector id: {definition.id}")
        connector_ids.add(definition.id)
        plugins.append(plugin)
    return plugins


def _validate_sdk_requirement(distribution: Any, sdk_name: str, sdk_version: str) -> None:
    if distribution is None:
        raise ValueError("connector entry point has no distribution metadata")
    distribution_name = canonicalize_name(distribution.metadata["Name"])
    for requirement_text in distribution.requires or []:
        requirement = Requirement(requirement_text)
        if canonicalize_name(requirement.name) != sdk_name:
            continue
        if requirement.marker is not None and not requirement.marker.evaluate():
            continue
        if sdk_version not in requirement.specifier:
            raise ValueError(
                f"{distribution_name} requires {requirement}, installed SDK is {sdk_version}"
            )
        return
    raise ValueError(
        f"{distribution_name} must declare an umbod requirement"
    )


def _coerce_plugin(value: Any) -> Optional[ConnectorPlugin]:
    if _looks_like_plugin(value):
        return value
    if callable(value):
        candidate = value()
        if _looks_like_plugin(candidate):
            return candidate
    return None


def _looks_like_plugin(value: Any) -> bool:
    return callable(getattr(value, "definition", None)) and callable(
        getattr(value, "registration", None)
    )


def _fail(message: str) -> NoReturn:
    typer.echo(message, err=True)
    raise typer.Exit(code=1)


app.command("validate")(ValidateCommand())
