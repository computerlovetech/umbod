import json
from pathlib import Path

import pytest

from umbod_desktop.backward_compatibility.profile import saved_legacy_port
from umbod_desktop.endpoint import no_saved_port, saved_port


@pytest.mark.parametrize("current", [{}, {"port": None}])
def test_missing_current_port_uses_composed_legacy_fallback(tmp_path: Path, current: dict[str, object]) -> None:
    (tmp_path / "python-endpoint.json").write_text(json.dumps(current))
    (tmp_path / "config.json").write_text('{"gateway_port":19432}')
    assert saved_port(tmp_path, saved_legacy_port) == 19432


def test_current_port_precedes_legacy_without_reading_it(tmp_path: Path) -> None:
    (tmp_path / "python-endpoint.json").write_text('{"port":19433}')
    (tmp_path / "config.json").write_text("invalid-json")
    assert saved_port(tmp_path, saved_legacy_port) == 19433


def test_permanent_port_reader_does_not_read_legacy_profile(tmp_path: Path) -> None:
    (tmp_path / "config.json").write_text('{"gateway_port":19432}')
    assert saved_port(tmp_path, no_saved_port) == 0


def test_absent_current_file_uses_composed_legacy_fallback(tmp_path: Path) -> None:
    (tmp_path / "config.json").write_text('{"gateway_port":19432}')
    assert saved_port(tmp_path, saved_legacy_port) == 19432


@pytest.mark.parametrize("port", [True, False, 0, -1, 65536, "19432", 19432.0])
@pytest.mark.parametrize("filename,field", [("python-endpoint.json", "port"), ("config.json", "gateway_port")])
def test_invalid_saved_port_is_rejected(tmp_path: Path, port: object, filename: str, field: str) -> None:
    (tmp_path / filename).write_text(json.dumps({field: port}))
    with pytest.raises(ValueError, match="Invalid saved local port"):
        saved_port(tmp_path, saved_legacy_port)


def test_no_saved_port_returns_ephemeral_port(tmp_path: Path) -> None:
    assert saved_port(tmp_path, saved_legacy_port) == 0
