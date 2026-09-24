from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
import typer

from umbod.cli import connectors


class FakeDistribution:
    def __init__(self, name: str, requirements: list[str]) -> None:
        self.metadata = {"Name": name}
        self.requires = requirements


class FakePlugin:
    def __init__(self, connector_id: str) -> None:
        self.connector_id = connector_id
        self.registration_calls = 0

    def definition(self) -> SimpleNamespace:
        return SimpleNamespace(id=self.connector_id)

    def registration(self) -> dict[str, Any]:
        self.registration_calls += 1
        raise AssertionError("registration must not run during deployment validation")


class FakeEntryPoint:
    def __init__(self, distribution: FakeDistribution, plugin: FakePlugin) -> None:
        self.dist = distribution
        self.plugin = plugin

    def load(self) -> FakePlugin:
        return self.plugin


def _configure_metadata(
    monkeypatch: pytest.MonkeyPatch,
    requirements: list[str],
    plugins: list[FakePlugin],
) -> None:
    distribution = FakeDistribution("example-plugins", requirements)
    entry_point_values = [FakeEntryPoint(distribution, plugin) for plugin in plugins]
    monkeypatch.setattr(connectors, "entry_points", lambda **kwargs: entry_point_values)
    monkeypatch.setattr(connectors, "version", lambda name: "0.1.0")
    monkeypatch.setattr(connectors, "validate_connector", lambda definition: None)


def test_validate_accepts_compatible_structurally_valid_plugins_without_registration(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    plugin = FakePlugin("valid")
    _configure_metadata(
        monkeypatch,
        ["umbod>=0.1,<0.2"],
        [plugin],
    )

    connectors.ValidateCommand()(plugin_path=None)

    assert plugin.registration_calls == 0
    assert capsys.readouterr().out == "Connector plugins valid: 1 loaded.\n"


def test_validate_rejects_incompatible_sdk_requirement(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _configure_metadata(
        monkeypatch,
        ["umbod>=0.2,<0.3"],
        [FakePlugin("invalid")],
    )

    with pytest.raises(typer.Exit) as raised:
        connectors.ValidateCommand()(plugin_path=None)

    assert raised.value.exit_code == 1
    assert "installed SDK is 0.1.0" in capsys.readouterr().err


def test_validate_rejects_duplicate_connector_ids(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _configure_metadata(
        monkeypatch,
        ["umbod>=0.1,<0.2"],
        [FakePlugin("duplicate"), FakePlugin("duplicate")],
    )

    with pytest.raises(typer.Exit) as raised:
        connectors.ValidateCommand()(plugin_path=None)

    assert raised.value.exit_code == 1
    assert "duplicate connector id: duplicate" in capsys.readouterr().err


def test_validate_rejects_bundled_connector_sdk_package(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    plugin_path = tmp_path / "plugins"
    (plugin_path / "umbod_sdk").mkdir(parents=True)

    with pytest.raises(typer.Exit) as raised:
        connectors.ValidateCommand()(plugin_path=plugin_path)

    assert raised.value.exit_code == 1
    assert "must not contain the connector SDK package" in capsys.readouterr().err
