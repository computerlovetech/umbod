from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from typer.testing import CliRunner

from umbod.cli.main import app
from umbod.config import LocalFilesystemContentConfig, S3FilesystemContentConfig
from umbod.core.filesystem import StorageFailure


@pytest.fixture
def configured_migration(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    content = S3FilesystemContentConfig(
        bucket="migration-bucket", region="us-east-1", endpoint_url="",
        prefix="files", addressing_style="auto",
    )
    monkeypatch.setattr(
        "umbod.cli.migrate.OperatorSettings",
        lambda **kwargs: SimpleNamespace(data_dir="/app/data", filesystem_content_directory="/configured/source"),
    )
    monkeypatch.setattr(
        "umbod.cli.migrate.build_app_config",
        lambda operator: SimpleNamespace(filesystem=SimpleNamespace(content=content)),
    )
    migration = AsyncMock(return_value=SimpleNamespace(
        copied=2, skipped=1, planned=0, total_bytes=12,
    ))
    monkeypatch.setattr("umbod.cli.migrate.migrate_local_content", migration)
    return migration


@pytest.mark.parametrize("dry_run", [False, True])
def test_migration_uses_explicit_source_and_configured_destination(
    configured_migration: AsyncMock, dry_run: bool,
) -> None:
    arguments = ["migrate", "files-to-s3", "--source", "/data/files", "--offline"]
    if dry_run:
        arguments.append("--dry-run")

    result = CliRunner().invoke(app, arguments)

    assert result.exit_code == 0, result.output
    configured_migration.assert_awaited_once()
    assert configured_migration.await_args is not None
    options = configured_migration.await_args.kwargs
    assert options["source"] == Path("/data/files")
    assert options["target"].bucket == "migration-bucket"
    assert options["target"].prefix == "files"
    assert options["dry_run"] is dry_run
    assert "Local files retained" in result.output
    assert ("Dry run" if dry_run else "Migration complete") in result.output


def test_migration_requires_offline_acknowledgement(configured_migration: AsyncMock) -> None:
    result = CliRunner().invoke(app, ["migrate", "files-to-s3", "--source", "/data/files"])

    assert result.exit_code == 2
    assert "Stop all file writers" in result.output
    configured_migration.assert_not_awaited()


def test_migration_rejects_local_destination(
    configured_migration: AsyncMock, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "umbod.cli.migrate.build_app_config",
        lambda operator: SimpleNamespace(filesystem=SimpleNamespace(
            content=LocalFilesystemContentConfig(directory=Path("/data/files")),
        )),
    )

    result = CliRunner().invoke(
        app, ["migrate", "files-to-s3", "--source", "/data/files", "--offline"],
    )

    assert result.exit_code == 2
    assert "configured S3" in result.output
    configured_migration.assert_not_awaited()


@pytest.mark.parametrize("directory,data_directory,expected", [
    ("/old/content", "/app/data", "/old/content"),
    (None, "/custom/data", "/custom/data/filesystem-content"),
])
def test_migration_defaults_to_configured_local_source(
    configured_migration: AsyncMock, monkeypatch: pytest.MonkeyPatch,
    directory: str | None, data_directory: str, expected: str,
) -> None:
    monkeypatch.setattr(
        "umbod.cli.migrate.OperatorSettings",
        lambda **kwargs: SimpleNamespace(
            data_dir=data_directory, filesystem_content_directory=directory,
        ),
    )

    result = CliRunner().invoke(app, ["migrate", "files-to-s3", "--offline"])

    assert result.exit_code == 0, result.output
    assert configured_migration.await_args is not None
    assert configured_migration.await_args.kwargs["source"] == Path(expected)


def test_missing_default_source_fails_without_creating_directory(
    configured_migration: AsyncMock, monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    from umbod.infrastructure import migrate_local_content

    missing = tmp_path / "missing"
    monkeypatch.setattr(
        "umbod.cli.migrate.OperatorSettings",
        lambda **kwargs: SimpleNamespace(data_dir=str(missing), filesystem_content_directory=None),
    )
    monkeypatch.setattr("umbod.cli.migrate.migrate_local_content", migrate_local_content)

    result = CliRunner().invoke(app, ["migrate", "files-to-s3", "--offline"])

    assert result.exit_code == 1
    assert not missing.exists()


@pytest.mark.parametrize("failure", [ValueError, StorageFailure, OSError])
def test_migration_failure_is_nonzero_and_does_not_expose_exception(
    configured_migration: AsyncMock, failure: type[Exception],
) -> None:
    configured_migration.side_effect = failure("private credential or payload")

    result = CliRunner().invoke(
        app, ["migrate", "files-to-s3", "--source", "/data/files", "--offline"],
    )

    assert result.exit_code == 1
    assert "Migration failed" in result.output
    assert "private credential" not in result.output
