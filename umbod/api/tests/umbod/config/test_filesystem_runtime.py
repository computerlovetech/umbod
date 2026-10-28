import json
import subprocess
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError
from pytest import MonkeyPatch

from umbod.config import (
    AppConfig,
    FilesystemRuntimeConfig,
    InMemoryFilesystemContentConfig,
    LocalFilesystemContentConfig,
    OperatorSettings,
    build_app_config,
    inspect_app_config,
    redact_app_config,
    safe_app_config_dump,
)


def test_embedded_filesystem_defaults_to_inmemory_content() -> None:
    config = AppConfig()

    assert isinstance(config.filesystem.content, InMemoryFilesystemContentConfig)
    assert config.filesystem.model_dump() == {
        "content": {"type": "inmemory"},
        "upload_max_bytes": 10 * 1024 * 1024,
    }


@pytest.mark.parametrize("store", ["inmemory", "sqlite"])
def test_operator_filesystem_content_is_local_and_independent_of_database(
    monkeypatch: MonkeyPatch, store: str
) -> None:
    monkeypatch.delenv("UMBOD_CONNECTOR_STORE_SQLITE_PATH", raising=False)
    monkeypatch.setenv("UMBOD_DATA_DIR", "/app/data/")
    monkeypatch.setenv("UMBOD_CONNECTOR_STORE", store)
    config = build_app_config(OperatorSettings(_env_file=None))

    assert isinstance(config.filesystem.content, LocalFilesystemContentConfig)
    assert config.filesystem.content.directory == Path("/app/data/filesystem-content")
    assert config.filesystem.upload_max_bytes == 10 * 1024 * 1024
    assert config.connector_store.type == store
    assert config.connector_store.sqlite_path == "/app/data/umbod.sqlite3"


def test_operator_default_filesystem_directory_is_under_default_data_directory() -> None:
    config = build_app_config(OperatorSettings(_env_file=None))

    assert config.filesystem.content == LocalFilesystemContentConfig(
        directory=Path(".data/filesystem-content")
    )


def test_operator_reads_explicit_content_directory_and_upload_limit(
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setenv("UMBOD_DATA_DIR", "/app/data")
    monkeypatch.setenv("UMBOD_FILESYSTEM_CONTENT_DIRECTORY", "content//files/")
    monkeypatch.setenv("UMBOD_FILESYSTEM_UPLOAD_MAX_BYTES", "4096")
    config = build_app_config(OperatorSettings(_env_file=None))

    assert config.filesystem.content == LocalFilesystemContentConfig(
        directory=Path("content/files")
    )
    assert config.filesystem.upload_max_bytes == 4096


@pytest.mark.parametrize("limit", [0, -1])
def test_embedded_upload_limit_rejects_nonpositive_values(limit: int) -> None:
    with pytest.raises(ValidationError, match="upload_max_bytes"):
        FilesystemRuntimeConfig(upload_max_bytes=limit)


@pytest.mark.parametrize("limit", ["0", "-1"])
def test_operator_upload_limit_rejects_nonpositive_environment_values(
    monkeypatch: MonkeyPatch, limit: str
) -> None:
    monkeypatch.setenv("UMBOD_FILESYSTEM_UPLOAD_MAX_BYTES", limit)

    with pytest.raises(ValidationError, match="filesystem_upload_max_bytes"):
        OperatorSettings(_env_file=None)


def test_upload_limit_accepts_one_byte() -> None:
    config = build_app_config(
        OperatorSettings(_env_file=None, filesystem_upload_max_bytes=1)
    )

    assert config.filesystem.upload_max_bytes == 1
    assert FilesystemRuntimeConfig(upload_max_bytes=1).upload_max_bytes == 1


@pytest.mark.parametrize("directory", ["", " ", "\t\n"])
def test_local_content_requires_nonblank_directory(directory: str) -> None:
    with pytest.raises(ValidationError, match="must not be blank"):
        LocalFilesystemContentConfig(directory=directory)

    with pytest.raises(ValidationError, match="must not be blank"):
        OperatorSettings(_env_file=None, filesystem_content_directory=directory)


@pytest.mark.parametrize("backend", ["local", "unsupported"])
def test_content_backend_requires_valid_discriminator_and_local_directory(
    backend: str,
) -> None:
    with pytest.raises(ValidationError):
        AppConfig(filesystem={"content": {"type": backend}})


def test_local_content_is_discriminated_and_serializable() -> None:
    config = AppConfig(
        filesystem={"content": {"type": "local", "directory": "content/files"}}
    )

    assert isinstance(config.filesystem.content, LocalFilesystemContentConfig)
    for document in (safe_app_config_dump(config), redact_app_config(config)):
        assert json.loads(json.dumps(document))["filesystem"]["content"] == {
            "type": "local",
            "directory": "content/files",
        }


def test_inspection_exposes_upload_limit_but_not_host_directory() -> None:
    config = AppConfig(filesystem=FilesystemRuntimeConfig(upload_max_bytes=123))
    entries = {
        entry.variable: entry
        for group in inspect_app_config(config).groups
        for entry in group.entries
    }

    assert entries["UMBOD_FILESYSTEM_UPLOAD_MAX_BYTES"].value == 123
    assert entries["UMBOD_FILESYSTEM_UPLOAD_MAX_BYTES"].type == "integer"
    assert "UMBOD_FILESYSTEM_CONTENT_DIRECTORY" not in entries


def test_configuration_import_does_not_load_infrastructure() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; import umbod.config; "
            "assert not any(name.startswith('umbod.infrastructure') for name in sys.modules)",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
