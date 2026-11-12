import json
from pathlib import Path
import re
import subprocess
import sys
from tempfile import TemporaryDirectory
from typing import Any


PREVIEW_ENVIRONMENT_KEY = "UMBOD_FILESYSTEM_PREVIEW_MAX_BYTES"
UPLOAD_ENVIRONMENT_KEY = "UMBOD_FILESYSTEM_UPLOAD_MAX_BYTES"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


def render(chart: str, values: dict[str, Any]) -> subprocess.CompletedProcess[str]:
    with TemporaryDirectory() as directory:
        path = Path(directory) / "values.json"
        path.write_text(json.dumps(values))
        return subprocess.run(
            ["helm", "template", "umbod", chart, "-f", str(path)],
            capture_output=True,
            text=True,
            check=False,
        )


def validate_environment(container: str, name: str, key: str, expected: int) -> None:
    matches = re.findall(rf'name: {key}\s+value: "([^"]+)"', container)
    require(matches == [str(expected)], f"{name} must receive exactly one shared {key}: {matches}")
    require(container.count(f"name: {key}\n") == 1, f"{name} must not duplicate {key}")


def validate_shared_limits(rendered: str, upload: int, preview: int) -> None:
    core = next(item for item in rendered.split("---") if "/templates/core-deployment.yaml" in item)
    frontend = next(item for item in rendered.split("---") if "/templates/frontend-deployment.yaml" in item)
    api, mcp = core.split("        - name: mcp\n")
    for name, container in (("API", api), ("MCP and administrator", mcp)):
        validate_environment(container, name, UPLOAD_ENVIRONMENT_KEY, upload)
        validate_environment(container, name, PREVIEW_ENVIRONMENT_KEY, preview)
    validate_environment(frontend, "frontend", PREVIEW_ENVIRONMENT_KEY, preview)
    require(UPLOAD_ENVIRONMENT_KEY not in frontend, "frontend must not receive the upload limit")


def validate_configured_limits(chart: str) -> None:
    baseline = render(chart, {})
    require(baseline.returncode == 0, baseline.stderr)
    validate_shared_limits(baseline.stdout, 10485760, 1048576)
    for limits, upload, preview in (
        ({"uploadMaxBytes": 11534336}, 11534336, 1048576),
        ({"previewMaxBytes": 2097152}, 10485760, 2097152),
        ({"uploadMaxBytes": 1, "previewMaxBytes": 9007199254740991}, 1, 9007199254740991),
        ({"uploadMaxBytes": 9007199254740991, "previewMaxBytes": 1}, 9007199254740991, 1),
    ):
        for hosting in ("shared", "separate"):
            result = render(chart, {
                "config": {"filesystem": limits},
                "core": {"mcp": {"administrator": {"hosting": hosting}}},
            })
            require(result.returncode == 0, result.stderr)
            validate_shared_limits(result.stdout, upload, preview)


def validate_invalid_limits(chart: str) -> None:
    for key in ("uploadMaxBytes", "previewMaxBytes"):
        for invalid in (0, -1, 1.5, "1048576", None, True, 9007199254740992, 9007199254740993):
            result = render(chart, {"config": {"filesystem": {key: invalid}}})
            require(result.returncode != 0, f"invalid {key} accepted: {invalid!r}")
            require(key in result.stderr, result.stderr)
            if invalid is None:
                require(any(marker in result.stderr for marker in ("required", "missing property")), f"missing {key} must be rejected: {result.stderr}")
    for invalid_filesystem in (None, 1, "limits", False, [], {"unknownMaxBytes": 1}):
        result = render(chart, {"config": {"filesystem": invalid_filesystem}})
        require(result.returncode != 0, f"invalid filesystem configuration accepted: {invalid_filesystem!r}")
        require("filesystem" in result.stderr, result.stderr)
    result = render(chart, {"config": {"filesystemPreviewMaxBytes": 1048576}})
    require(result.returncode != 0, "obsolete flat preview limit accepted")
    require("filesystemPreviewMaxBytes" in result.stderr, result.stderr)


def validate_managed_environment(chart: str) -> None:
    for component in ("api", "mcp"):
        for key in (UPLOAD_ENVIRONMENT_KEY, PREVIEW_ENVIRONMENT_KEY):
            result = render(chart, {"core": {component: {"env": {key: "2097152"}}}})
            require(result.returncode != 0, f"{component} managed {key} override accepted")
            require(key in result.stderr, result.stderr)


def main() -> None:
    chart = sys.argv[1]
    validate_configured_limits(chart)
    validate_invalid_limits(chart)
    validate_managed_environment(chart)


if __name__ == "__main__":
    main()
