from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import cast

import pytest
from botocore.exceptions import ClientError

from umbod.core.filesystem import StorageFailure
from umbod.infrastructure.filesystem.migration.adapters import LocalMigrationSource, S3MigrationTarget
from umbod.infrastructure.filesystem.migration.service import migrate_content
from umbod.infrastructure.filesystem.s3.edge import S3Client
from tests.umbod.infrastructure.filesystem.test_s3_content import (
    FakeBackend, FakeClient, collect, configuration,
)
from tests.umbod.infrastructure.filesystem.migration.test_filesystem_migration_service import KEY, MemoryStore


@pytest.mark.asyncio
async def test_local_copy_preserves_all_objects_and_temporary_files(tmp_path: Path) -> None:
    (tmp_path / KEY).write_bytes(b"unreferenced")
    (tmp_path / (".content-temporary")).write_bytes(b"partial")
    target = MemoryStore({})
    result = await migrate_content(LocalMigrationSource(tmp_path), target, False)
    assert result.copied == 1
    assert target.objects == {KEY: b"unreferenced"}
    assert (tmp_path / KEY).read_bytes() == b"unreferenced"
    assert (tmp_path / ".content-temporary").read_bytes() == b"partial"


def test_missing_source_is_not_created(tmp_path: Path) -> None:
    missing = tmp_path / "absent"
    with pytest.raises(StorageFailure):
        LocalMigrationSource(missing)
    assert not missing.exists()


def test_symlink_root_is_rejected(tmp_path: Path) -> None:
    link = tmp_path / "link"
    link.symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(StorageFailure):
        LocalMigrationSource(link)


@pytest.mark.asyncio
@pytest.mark.parametrize("entry", ["malformed", "directory", "symlink", "temporary_symlink"])
async def test_preflight_rejects_invalid_entries_before_any_write(tmp_path: Path, entry: str) -> None:
    (tmp_path / KEY).write_bytes(b"data")
    if entry == "directory":
        (tmp_path / ("b" * 32)).mkdir()
    elif entry in ("symlink", "temporary_symlink"):
        name = ".content-link" if entry == "temporary_symlink" else "b" * 32
        (tmp_path / name).symlink_to(tmp_path / KEY)
    else:
        (tmp_path / "malformed").write_bytes(b"data")
    target = MemoryStore({})
    with pytest.raises(StorageFailure):
        await migrate_content(LocalMigrationSource(tmp_path), target, False)
    assert target.writes == 0


class HeadClient(FakeClient):
    async def head_object(self, **kwargs: object) -> object:
        await self._call("head", kwargs)
        if cast(str, kwargs["Key"]) not in self.backend.objects:
            raise ClientError({"Error": {"Code": self.backend.malformed or "404"}}, "HeadObject")
        return {}


@pytest.mark.asyncio
@pytest.mark.parametrize("code,missing", [("404", True), ("NoSuchKey", True), ("403", False), ("500", False), ("NotFound", False)])
async def test_s3_head_distinguishes_only_missing_errors(code: str, missing: bool) -> None:
    backend = FakeBackend()
    backend.malformed = code

    @asynccontextmanager
    async def provider() -> AsyncGenerator[S3Client]:
        yield cast(S3Client, HeadClient(backend))

    config = configuration().model_copy(update={"prefix": "scoped"})
    target = S3MigrationTarget(config, provider)
    if missing:
        assert await target.exists(KEY) is False
    else:
        with pytest.raises(StorageFailure, match="Cannot inspect migration destination"):
            await target.exists(KEY)
    assert backend.calls == [("head", {"Bucket": config.bucket, "Key": f"scoped/{KEY}"})]


@pytest.mark.asyncio
async def test_s3_keyed_write_reads_back_and_never_overwrites() -> None:
    backend = FakeBackend()
    target = S3MigrationTarget(configuration(), backend.provider)
    source = MemoryStore({KEY: b"data"})
    await target.write_at(KEY, source.get(KEY))
    assert await collect(target.get(KEY)) == b"data"
    with pytest.raises(StorageFailure):
        await target.write_at(KEY, MemoryStore({KEY: b"other"}).get(KEY))
    assert backend.objects == {KEY: b"data"}
    with pytest.raises(StorageFailure, match="Invalid content key"):
        await target.write_at("../invalid", source.get(KEY))


@pytest.mark.asyncio
@pytest.mark.parametrize("data", [b"", b"small", b"multipart" * 8])
async def test_local_to_s3_copy_and_resume_with_prefix(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, data: bytes,
) -> None:
    monkeypatch.setattr("umbod.infrastructure.filesystem.s3_content.PART_SIZE", 8)
    (tmp_path / KEY).write_bytes(data)
    backend = FakeBackend()

    @asynccontextmanager
    async def provider() -> AsyncGenerator[S3Client]:
        yield cast(S3Client, HeadClient(backend))

    target = S3MigrationTarget(configuration().model_copy(update={"prefix": "scoped"}), provider)
    source = LocalMigrationSource(tmp_path)

    result = await migrate_content(source, target, False)
    resumed = await migrate_content(source, target, False)

    assert result.copied == 1
    assert result.total_bytes == len(data)
    assert resumed.skipped == 1
    assert backend.objects == {f"scoped/{KEY}": data}
    assert (tmp_path / KEY).read_bytes() == data
    assert all(body.closed for body in backend.bodies)
    assert not backend.uploads


class ConcurrentPublicationClient(HeadClient):
    async def head_object(self, **kwargs: object) -> object:
        self.backend.objects[cast(str, kwargs["Key"])] = b"competing content"
        raise ClientError({"Error": {"Code": "404"}}, "HeadObject")


@pytest.mark.asyncio
@pytest.mark.parametrize("data", [b"small", b"multipart" * 8])
async def test_concurrent_destination_publication_is_preserved(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, data: bytes,
) -> None:
    monkeypatch.setattr("umbod.infrastructure.filesystem.s3_content.PART_SIZE", 8)
    (tmp_path / KEY).write_bytes(data)
    backend = FakeBackend()

    @asynccontextmanager
    async def provider() -> AsyncGenerator[S3Client]:
        yield cast(S3Client, ConcurrentPublicationClient(backend))

    target = S3MigrationTarget(configuration(), provider)

    with pytest.raises(StorageFailure):
        await migrate_content(LocalMigrationSource(tmp_path), target, False)

    assert backend.objects == {KEY: b"competing content"}
    assert not backend.uploads
    assert backend.aborts == (1 if len(data) > 8 else 0)
