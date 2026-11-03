from __future__ import annotations

import subprocess
from collections.abc import Sequence
from pathlib import Path

import pytest

from scripts.run_tests import main


class RecordingRunner:
    def __init__(self, exit_code: int) -> None:
        self.exit_code = exit_code
        self.calls: list[tuple[tuple[str, ...], Path, bool]] = []

    def __call__(
        self, command: Sequence[str], *, cwd: Path, check: bool,
    ) -> subprocess.CompletedProcess[bytes]:
        self.calls.append((tuple(command), cwd, check))
        return subprocess.CompletedProcess(command, self.exit_code)


@pytest.mark.parametrize(("module", "target"), [
    ("all", "tests"),
    ("cli", "tests/umbod/cli"),
    ("config", "tests/umbod/config"),
    ("core", "tests/umbod/core"),
    ("hosting", "tests/umbod/hosting"),
    ("infrastructure", "tests/umbod/infrastructure"),
    ("mcp", "tests/umbod/mcp"),
    ("rest", "tests/umbod/rest"),
    ("messaging", "tests/messaging"),
    ("deployment", "tests/deployment"),
])
def test_module_selects_directory_with_automatic_workers(module: str, target: str) -> None:
    runner = RecordingRunner(0)
    assert main([module], runner) == 0
    assert runner.calls == [(
        ("uv", "run", "--locked", "pytest", target, "-q", "-n", "auto", "--dist=worksteal"),
        Path(__file__).resolve().parents[2] / "api",
        False,
    )]


@pytest.mark.parametrize("separator", [[], ["--"]], ids=["direct", "separator"])
def test_additional_pytest_arguments_are_forwarded_without_shell_parsing(separator: list[str]) -> None:
    runner = RecordingRunner(0)
    arguments = ["-n", "0", "-k", "health or authentication", "--cov", "--maxfail=1"]
    assert main(["rest", *separator, *arguments], runner) == 0
    assert runner.calls[0][0][9:] == tuple(arguments)


@pytest.mark.parametrize("arguments", [["--analyse", "core"], ["core", "--analyse"]])
def test_analysis_reports_ten_slowest_phases(arguments: list[str]) -> None:
    runner = RecordingRunner(0)
    assert main(arguments, runner) == 0
    assert runner.calls[0][0][9:] == ("--durations=10", "--durations-min=0.01")


@pytest.mark.parametrize("separator", [[], ["--"]], ids=["direct", "separator"])
def test_analysis_defaults_can_be_overridden_with_pytest_arguments(separator: list[str]) -> None:
    runner = RecordingRunner(0)
    arguments = ["--durations=25", "--durations-min=0", "-n", "0"]
    assert main(["core", "--analyse", *separator, *arguments], runner) == 0
    assert runner.calls[0][0][9:] == ("--durations=10", "--durations-min=0.01", *arguments)


@pytest.mark.parametrize("argument", ["--help", "--analyse"])
def test_separator_prevents_runner_from_consuming_pytest_arguments(argument: str) -> None:
    runner = RecordingRunner(0)
    assert main(["core", "--", argument], runner) == 0
    assert runner.calls[0][0][9:] == (argument,)


@pytest.mark.parametrize("analyse", [False, True], ids=["normal", "analysis"])
@pytest.mark.parametrize("exit_code", [0, 1, 2, 3, 4, 5])
def test_pytest_exit_code_is_preserved(exit_code: int, analyse: bool) -> None:
    arguments = ["all", "--analyse"] if analyse else ["all"]
    assert main(arguments, RecordingRunner(exit_code)) == exit_code


@pytest.mark.parametrize("arguments", [[], ["unknown"], ["frontend"], ["lint"]])
def test_invalid_selection_does_not_launch_a_process(arguments: list[str]) -> None:
    runner = RecordingRunner(0)
    with pytest.raises(SystemExit) as error:
        main(arguments, runner)
    assert error.value.code == 2
    assert runner.calls == []


def test_help_does_not_launch_a_process(capsys: pytest.CaptureFixture[str]) -> None:
    runner = RecordingRunner(0)
    with pytest.raises(SystemExit) as error:
        main(["--help"], runner)
    assert error.value.code == 0
    help_text = capsys.readouterr().out
    assert "rest" in help_text
    assert "uv run --locked pytest" in help_text
    assert "-n auto" in help_text
    assert "--dist=worksteal" in help_text
    assert "Coverage is off unless --cov is supplied." in help_text
    assert "paths are relative to umbod/api" in help_text
    assert "--analyse" in help_text
    assert "--durations=10 --durations-min=0.01" in help_text
    assert "not accumulated fixture costs" in help_text
    assert runner.calls == []


def test_missing_uv_reports_an_actionable_error(capsys: pytest.CaptureFixture[str]) -> None:
    def missing_uv(
        command: Sequence[str], *, cwd: Path, check: bool,
    ) -> subprocess.CompletedProcess[bytes]:
        raise FileNotFoundError

    with pytest.raises(SystemExit) as error:
        main(["all"], missing_uv)
    assert error.value.code == 127
    assert "uv is required" in capsys.readouterr().err


def test_keyboard_interrupt_returns_interrupt_exit_code() -> None:
    def interrupted(
        command: Sequence[str], *, cwd: Path, check: bool,
    ) -> subprocess.CompletedProcess[bytes]:
        raise KeyboardInterrupt

    assert main(["all"], interrupted) == 130
