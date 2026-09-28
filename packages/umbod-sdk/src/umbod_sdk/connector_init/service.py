import re
import tomllib
from keyword import iskeyword
from pathlib import Path

from umbod_sdk.connector_init.models import InitPlan, InitRequest
from umbod_sdk.connector_init.port import InitError, ProjectFiles

_NAME = re.compile(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*\Z")
_MODULE_PART = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")


def _table(parent: dict[str, object], key: str, parent_path: str) -> dict[str, object]:
    path = f"{parent_path}.{key}" if parent_path else key
    value = parent.get(key, {})
    if not isinstance(value, dict):
        raise InitError(f"pyproject.toml [{path}] must be a table")
    return value


def _validate_request(request: InitRequest) -> tuple[str, str]:
    if not _NAME.fullmatch(request.name):
        raise InitError("--name must be lowercase words separated by hyphens")
    parts = request.module.split(".")
    if len(parts) != 2 or any(
        not _MODULE_PART.fullmatch(part) or iskeyword(part) or part == "__init__" for part in parts
    ):
        raise InitError("--module must be two ASCII Python identifiers: an existing package and a new module")
    return parts[0], parts[1]


def _validate_hatch(metadata: dict[str, object], package: str) -> None:
    build = _table(metadata, "build-system", "")
    if build.get("build-backend") != "hatchling.build":
        raise InitError("[build-system].build-backend must be hatchling.build")
    tool = _table(metadata, "tool", "")
    hatch = _table(tool, "hatch", "tool")
    hatch_build = _table(hatch, "build", "tool.hatch")
    targets = _table(hatch_build, "targets", "tool.hatch.build")
    wheel = _table(targets, "wheel", "tool.hatch.build.targets")
    packages = wheel.get("packages")
    if not isinstance(packages, list) or any(not isinstance(item, str) for item in packages):
        raise InitError("[tool.hatch.build.targets.wheel].packages must be a list of strings")
    if f"src/{package}" not in packages:
        raise InitError(f"Explicit Hatch wheel packages = [\"src/{package}\"] is required")


def _metadata_addition(metadata_bytes: bytes, package: str, request: InitRequest) -> bytes:
    try:
        text = metadata_bytes.decode("utf-8")
        metadata = tomllib.loads(text)
    except (UnicodeError, tomllib.TOMLDecodeError) as error:
        raise InitError(f"pyproject.toml must be readable UTF-8 TOML: {error}") from error
    project = metadata.get("project")
    if not isinstance(project, dict):
        raise InitError("pyproject.toml requires a [project] table")
    dynamic = project.get("dynamic", [])
    if not isinstance(dynamic, list) or any(not isinstance(item, str) for item in dynamic):
        raise InitError("[project].dynamic must be a list of strings")
    if "entry-points" in dynamic:
        raise InitError("Dynamic entry-points are not supported")
    entry_points = project.get("entry-points", {})
    if not isinstance(entry_points, dict) or "umbod.connectors" in entry_points:
        raise InitError("Existing or malformed connector entry-point group")
    _validate_hatch(metadata, package)
    addition = ("" if not metadata_bytes or metadata_bytes.endswith(b"\n") else "\n") + (
        f"\n[project.entry-points.\"umbod.connectors\"]\n"
        f"{request.name} = \"{request.module}:plugin\"\n"
    )
    try:
        tomllib.loads(text + addition)
    except tomllib.TOMLDecodeError as error:
        raise InitError(f"Cannot append connector entry-point table: {error}") from error
    return addition.encode("utf-8")


def _source(name: str) -> str:
    display_name = name.replace("-", " ").title()
    return (
        "from typing import Annotated\n\n"
        "from pydantic import ConfigDict, Field\n"
        "from umbod_sdk.connectors.plugin_api import Connector, ConfigurationCheckResult\n"
        "from umbod_sdk.connectors.proxies import Model\n\n\n"
        "class HelloWorldConfiguration(Model):\n"
        "    model_config = ConfigDict(extra=\"forbid\")\n\n\n"
        "connector = Connector(\n"
        f"    id=\"{name}\",\n"
        f"    name=\"{display_name}\",\n"
        "    description=\"Greets people with a hello world message.\",\n"
        "    capability_description=\"Say hello to a person.\",\n"
        "    configuration=HelloWorldConfiguration,\n"
        ")\n\n\n"
        "@connector.configuration_check\n"
        "def check_configuration(configuration: HelloWorldConfiguration) -> ConfigurationCheckResult:\n"
        "    return ConfigurationCheckResult.valid()\n\n\n"
        "@connector.tool(description=\"Greet a person by name.\")\n"
        "def say_hello(\n"
        "    name: Annotated[str, Field(description=\"Name of the person to greet.\")],\n"
        "    configuration: HelloWorldConfiguration,\n"
        ") -> str:\n"
        "    return f\"Hello, {name}!\"\n\n\n"
        "plugin = connector\n"
    )


class ConnectorInitializer:
    def __init__(self, files: ProjectFiles) -> None:
        self._files = files

    def plan(self, request: InitRequest) -> InitPlan:
        package, module = _validate_request(request)
        snapshot = self._files.inspect(request)
        addition = _metadata_addition(snapshot.metadata, package, request)
        project_path = Path(request.project_directory)
        return InitPlan(
            request=request,
            original_metadata=snapshot.metadata,
            metadata_addition=addition,
            source=_source(request.name),
            module_path=str(project_path / "src" / package / f"{module}.py"),
            metadata_path=str(project_path / "pyproject.toml"),
        )

    def apply(self, plan: InitPlan) -> None:
        if self.plan(plan.request) != plan:
            raise InitError("Project changed since preview; no files were written")
        source = plan.source.encode("utf-8")
        self._files.create_module(plan.request, source)
        try:
            self._files.append_metadata(plan.request, plan.original_metadata, plan.metadata_addition)
        except (OSError, InitError) as error:
            raise InitError(
                f"Metadata update failed ({error}); module may remain at {plan.module_path}; "
                f"inspect {plan.metadata_path} and the module for partial changes. "
                "No automatic cleanup was attempted."
            ) from error
