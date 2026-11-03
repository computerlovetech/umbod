from __future__ import annotations

import argparse
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Protocol


TEST_MODULES: dict[str, str] = {
    "all": "tests",
    "cli": "tests/umbod/cli",
    "config": "tests/umbod/config",
    "core": "tests/umbod/core",
    "hosting": "tests/umbod/hosting",
    "infrastructure": "tests/umbod/infrastructure",
    "mcp": "tests/umbod/mcp",
    "rest": "tests/umbod/rest",
    "messaging": "tests/messaging",
    "deployment": "tests/deployment",
}


class ProcessRunner(Protocol):
    def __call__(
        self, command: Sequence[str], *, cwd: Path, check: bool,
    ) -> subprocess.CompletedProcess[bytes]: ...


def main(arguments: Sequence[str], runner: ProcessRunner = subprocess.run) -> int:
    parser = argparse.ArgumentParser(
        description="Run Python pytest tests for a backend source module.",
        usage="%(prog)s [--analyse] module [pytest arguments]",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        allow_abbrev=False,
        epilog=(
            "Defaults: uv run --locked pytest with quiet output (-q), automatic\n"
            "workers (-n auto), and work-stealing (--dist=worksteal).\n"
            "Tests run from umbod/api regardless of the caller's working directory.\n"
            "Coverage is off unless --cov is supplied.\n"
            "Additional pytest arguments follow the module; paths are relative to umbod/api.\n"
            "Arguments after -- are forwarded unchanged to pytest.\n"
            "Analysis shows the 10 slowest setup, call, or teardown phases taking at\n"
            "least 0.01s (--durations=10 --durations-min=0.01), sorted slowest first.\n"
            "These are individual phase timings, not accumulated fixture costs.\n"
            "Forwarded pytest arguments can override these defaults."
        ),
    )
    parser.add_argument("module", choices=TEST_MODULES, help="Required backend module; all selects the complete suite.")
    parser.add_argument(
        "--analyse", action="store_true",
        help="Report the slowest test phases; accepted before or after the module.",
    )
    options, pytest_args = parser.parse_known_args(arguments)
    if pytest_args[:1] == ["--"]:
        pytest_args = pytest_args[1:]
    analysis_args = ["--durations=10", "--durations-min=0.01"] if options.analyse else []
    command = [
        "uv", "run", "--locked", "pytest", TEST_MODULES[options.module],
        "-q", "-n", "auto", "--dist=worksteal", *analysis_args, *pytest_args,
    ]
    try:
        return runner(command, cwd=Path(__file__).resolve().parents[1] / "api", check=False).returncode
    except FileNotFoundError:
        parser.exit(127, "uv is required but was not found on PATH.\n")
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
