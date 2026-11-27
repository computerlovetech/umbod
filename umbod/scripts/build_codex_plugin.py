from __future__ import annotations

import argparse
import shlex
import shutil
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "api/src"))

from umbod.core.harness_plugins.rendering import (
    PLUGIN_VERSION as PLUGIN_VERSION,
    is_loopback as is_loopback,
    marketplace_name as marketplace_name,
    normalize_endpoint as normalize_endpoint,
    render_package as render_harness_package,
)
REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
RUN_DIAGNOSTICS_SKILL_PATH = REPOSITORY_ROOT / "skills/integrations/run-diagnostics/SKILL.md"


def render_package(
    endpoint: str, license_text: str, run_diagnostics_skill: str,
) -> Mapping[str, str]:
    return render_harness_package(endpoint, license_text, "codex", run_diagnostics_skill)


def write_package(destination: Path, files: Mapping[str, str]) -> None:
    for name in files:
        relative = Path(name)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("Package entries must stay inside the destination")
    destination.mkdir(parents=True, exist_ok=False)
    try:
        for name, content in files.items():
            path = destination / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
    except OSError:
        shutil.rmtree(destination)
        raise


def build_package(endpoint: str, destination: Path) -> str:
    files = render_package(
        endpoint,
        (REPOSITORY_ROOT / "LICENSE").read_text(encoding="utf-8"),
        RUN_DIAGNOSTICS_SKILL_PATH.read_text(encoding="utf-8"),
    )
    write_package(destination, files)
    return marketplace_name(endpoint)


def main(arguments: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build an endpoint-specific Umbod marketplace for Codex CLI")
    parser.add_argument("--endpoint", required=True, help="Umbod MCP URL or deployment origin")
    parser.add_argument("--output", required=True, type=Path, help="New marketplace directory; existing paths are never replaced")
    options = parser.parse_args(arguments)
    destination = options.output.expanduser().resolve()
    try:
        name = build_package(options.endpoint, destination)
    except (ValueError, OSError) as error:
        parser.exit(1, f"Could not build the Codex plugin: {error}\n")
    print(f"codex plugin marketplace add {shlex.quote(str(destination))}")
    print(f"codex plugin add umbod@{name}")
    print("Start a new Codex session and inspect /mcp. If sign-in is required, run: codex mcp login umbod")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
