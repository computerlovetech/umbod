from pathlib import Path

import pytest
from typer.testing import CliRunner

from umbod_sdk.cli import app

_METADATA = '[project.entry-points."umbod.connectors"]\nplugin = "never_import_this_module:Plugin"\n'


def test_check_defaults_to_current_directory_and_does_not_modify_project(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    metadata = tmp_path / "pyproject.toml"
    metadata.write_text(_METADATA)
    lockfile = tmp_path / "uv.lock"
    lockfile.write_text("original")
    monkeypatch.chdir(tmp_path)
    before = {path.name: path.read_bytes() for path in tmp_path.iterdir()}

    result = CliRunner().invoke(app, ["connectors", "check"], catch_exceptions=False)

    assert result.exit_code == 0, result.output
    assert "1 entry(s)" in result.output
    assert "Runtime loading and target-release compatibility were not checked" in result.output
    assert {path.name: path.read_bytes() for path in tmp_path.iterdir()} == before


def test_check_uses_explicit_project_and_does_not_import_target(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(_METADATA)
    result = CliRunner().invoke(app, ["connectors", "check", "--project", str(tmp_path)], catch_exceptions=False)
    assert result.exit_code == 0, result.output
    assert str(tmp_path / "pyproject.toml") in result.output


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (b"\xff", "cannot read UTF-8 metadata"),
        (b"[project\n", "malformed TOML"),
        (b'[project.entry-points."umbod.connectors"]\n', "at least one entry"),
    ],
)
def test_check_reports_invalid_file_without_traceback(tmp_path: Path, raw: bytes, expected: str) -> None:
    (tmp_path / "pyproject.toml").write_bytes(raw)
    result = CliRunner().invoke(app, ["connectors", "check", "--project", str(tmp_path)], catch_exceptions=False)
    assert result.exit_code == 1
    assert expected in result.output
    assert str(tmp_path / "pyproject.toml") in result.output
    assert "Traceback" not in result.output


def test_check_reports_missing_file(tmp_path: Path) -> None:
    result = CliRunner().invoke(app, ["connectors", "check", "--project", str(tmp_path)], catch_exceptions=False)
    assert result.exit_code == 1
    assert "pyproject.toml" in result.output
    assert "cannot read" in result.output


def test_check_reports_permission_failure_without_relying_on_os_user(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "pyproject.toml"
    path.write_text(_METADATA)

    def deny_read(self: Path, encoding: str) -> str:
        raise PermissionError("access denied")

    monkeypatch.setattr(Path, "read_text", deny_read)
    result = CliRunner().invoke(app, ["connectors", "check", "--project", str(tmp_path)], catch_exceptions=False)
    assert result.exit_code == 1
    assert "access denied" in result.output
    assert str(path) in result.output
