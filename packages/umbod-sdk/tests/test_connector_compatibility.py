import json
from importlib import import_module
from pathlib import Path

import pytest
from typer.testing import CliRunner

from umbod_sdk.cli import app
from umbod_sdk.connector_checks import (
    InMemoryMetadataReader,
    MetadataContent,
    MetadataRequest,
)
from umbod_sdk.connector_checks.checker import MetadataCheckError
from umbod_sdk.connector_checks.compatibility import (
    ConnectorCompatibilityChecker,
    InMemorySdkReleaseMetadataReader,
    SdkCompatibilityChecker,
    SdkVersion,
)


def _metadata(requirements: list[str]) -> str:
    return (
        '[project]\ndependencies = ' + json.dumps(requirements) + '\n'
        '[project.entry-points."umbod.connectors"]\nsample = "never_import:plugin"\n'
    )


@pytest.mark.parametrize(
    ("requirement", "version", "compatible"),
    [
        ("umbod>=0.1.0,<0.2.0", "0.1.5", True),
        ("umbod>=0.1.0,<0.2.0", "0.2.0", False),
        ("umbod>=0.1.0,<0.2.0", "0.0.9", False),
        ("UMBOD>=0.1.1b1,<0.2.0", "0.1.1b2", True),
        ("umbod>=0.1.1", "0.1.1b2", False),
        ("umbod>=0.1.0,<0.2.0", "0.1.1b1", True),
        ("umbod==0.1.1b2", "0.1.1b3", False),
    ],
)
def test_declared_sdk_range_acceptance(requirement: str, version: str, compatible: bool) -> None:
    checker: SdkCompatibilityChecker = ConnectorCompatibilityChecker(
        InMemoryMetadataReader(MetadataContent(text=_metadata([requirement])))
    )
    result = checker.check(MetadataRequest(project_directory="."), SdkVersion(version=version))
    assert result.compatible is compatible
    assert result.sdk_version == version


@pytest.mark.parametrize(
    ("requirements", "message"),
    [
        ([], "exactly one"),
        (["httpx>=0.1"], "exactly one"),
        (["umbod>=0.1", "UMBOD<1"], "exactly one"),
        (["umbod"], "specifier"),
        (["umbod @ https://example.com/sdk.whl"], "direct URL"),
        (["umbod>=0.1; python_version >= '3.14'"], "conditional"),
        (["not a requirement ???"], "malformed dependency"),
    ],
)
def test_unsupported_dependency_declarations_fail(requirements: list[str], message: str) -> None:
    checker: SdkCompatibilityChecker = ConnectorCompatibilityChecker(
        InMemoryMetadataReader(MetadataContent(text=_metadata(requirements)))
    )
    with pytest.raises(MetadataCheckError, match=message):
        checker.check(MetadataRequest(project_directory="."), SdkVersion(version="0.1.0"))


@pytest.mark.parametrize("dynamic", ['["dependencies"]', '"dependencies"', '[1]'])
def test_dynamic_or_malformed_dependency_metadata_fails(dynamic: str) -> None:
    text = _metadata(["umbod>=0.1"]).replace("[project]\n", f"[project]\ndynamic = {dynamic}\n")
    checker: SdkCompatibilityChecker = ConnectorCompatibilityChecker(InMemoryMetadataReader(MetadataContent(text=text)))
    with pytest.raises(MetadataCheckError, match="dynamic"):
        checker.check(MetadataRequest(project_directory="."), SdkVersion(version="0.1.0"))


@pytest.mark.parametrize("value", ['"umbod>=0.1"', '[1]', '{}'])
def test_dependency_list_must_contain_strings(value: str) -> None:
    text = _metadata([]).replace("dependencies = []", f"dependencies = {value}")
    checker: SdkCompatibilityChecker = ConnectorCompatibilityChecker(InMemoryMetadataReader(MetadataContent(text=text)))
    with pytest.raises(MetadataCheckError, match="static list"):
        checker.check(MetadataRequest(project_directory="."), SdkVersion(version="0.1.0"))


@pytest.fixture
def project(tmp_path: Path) -> Path:
    (tmp_path / "pyproject.toml").write_text(_metadata(["umbod>=0.1,<0.2"]))
    (tmp_path / "uv.lock").write_text("preserve lock")
    (tmp_path / "never_import.py").write_text('raise RuntimeError("must not import")')
    return tmp_path


def test_explicit_sdk_cli_is_read_only_and_offline(project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cli = import_module("umbod_sdk.connector_checks.cli")

    def reject_network() -> None:
        pytest.fail("Offline check accessed release metadata")

    monkeypatch.setattr(cli, "create_release_reader", reject_network)
    before = {path.name: path.read_bytes() for path in project.iterdir()}
    result = CliRunner().invoke(app, ["connectors", "check", "--project", str(project), "--sdk-version", "0.1.5"], catch_exceptions=False)
    assert result.exit_code == 0, result.output
    assert "image not verified" in result.output
    assert "Runtime loading" in result.output
    assert {path.name: path.read_bytes() for path in project.iterdir()} == before


@pytest.mark.parametrize("version", ["0.2.0", "latest", ""])
def test_bad_sdk_cli_target_fails_without_traceback(project: Path, version: str) -> None:
    result = CliRunner().invoke(app, ["connectors", "check", "--project", str(project), "--sdk-version", version], catch_exceptions=False)
    assert result.exit_code == 1
    assert "Traceback" not in result.output


def test_cli_target_uses_release_reader(project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    reader = InMemorySdkReleaseMetadataReader({"0.1.1-beta.1": SdkVersion(version="0.1.1b1")})
    monkeypatch.setattr("umbod_sdk.connector_checks.cli.create_release_reader", lambda: reader)
    result = CliRunner().invoke(app, ["connectors", "check", "--project", str(project), "--target", "0.1.1-beta.1"], catch_exceptions=False)
    assert result.exit_code == 0, result.output
    assert "accepts SDK 0.1.1b1 (published target 0.1.1-beta.1)" in result.output


def test_cli_rejects_conflicting_options(project: Path) -> None:
    result = CliRunner().invoke(app, ["connectors", "check", "--project", str(project), "--target", "0.1.1", "--sdk-version", "0.1.0"])
    assert result.exit_code == 2


def test_cli_missing_release_metadata_does_not_claim_success(project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    reader = InMemorySdkReleaseMetadataReader({})
    monkeypatch.setattr("umbod_sdk.connector_checks.cli.create_release_reader", lambda: reader)
    result = CliRunner().invoke(app, ["connectors", "check", "--project", str(project), "--target", "0.1.1"], catch_exceptions=False)
    assert result.exit_code == 1
    assert "no SDK version metadata" in result.output
