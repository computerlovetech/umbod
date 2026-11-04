import asyncio
from collections.abc import AsyncGenerator
from typing import cast

import pytest

from umbod.core.filesystem import StorageFailure
from umbod.infrastructure.filesystem.migration.ports import MigrationKeys, MigrationStream
from umbod.infrastructure.filesystem.migration.service import migrate_content

KEY = "a" * 32


class MemoryStore:
    def __init__(self, objects: dict[str, bytes]) -> None:
        self.objects = objects.copy()
        self.closed = 0
        self.writes = 0
        self.corrupt = False
        self.cancel = False

    async def list_keys(self) -> MigrationKeys:
        return MigrationKeys(keys=tuple(self.objects))

    def get(self, key: str) -> MigrationStream:
        return cast(MigrationStream, self._read(key))

    async def _read(self, key: str) -> AsyncGenerator[bytes, None]:
        try:
            yield self.objects[key]
        finally:
            self.closed += 1

    async def exists(self, key: str) -> bool:
        return key in self.objects

    async def write_at(self, key: str, stream: MigrationStream) -> None:
        self.writes += 1
        async for chunk in stream:
            if self.cancel:
                raise asyncio.CancelledError()
            self.objects[key] = b"corrupt" if self.corrupt else chunk


@pytest.mark.asyncio
async def test_copy_then_resume_verifies_existing_content() -> None:
    source = MemoryStore({KEY: b"data"})
    target = MemoryStore({})
    result = await migrate_content(source, target, False)
    assert result.model_dump() == dict(copied=1, skipped=0, planned=0, total_bytes=4)
    resumed = await migrate_content(source, target, False)
    assert resumed.skipped == 1
    assert target.writes == 1
    assert source.closed == 3


@pytest.mark.asyncio
@pytest.mark.parametrize("dry_run", [False, True])
async def test_conflicting_existing_content_is_never_overwritten(dry_run: bool) -> None:
    target = MemoryStore({KEY: b"conflict"})
    with pytest.raises(StorageFailure, match="conflicts"):
        await migrate_content(MemoryStore({KEY: b"data"}), target, dry_run)
    assert target.writes == 0
    assert target.objects[KEY] == b"conflict"
    assert target.closed == 1


@pytest.mark.asyncio
async def test_dry_run_plans_absent_objects_without_writes() -> None:
    target = MemoryStore({})
    result = await migrate_content(MemoryStore({KEY: b"data"}), target, True)
    assert result.model_dump() == dict(copied=0, skipped=0, planned=1, total_bytes=4)
    assert target.objects == {}


@pytest.mark.asyncio
async def test_empty_object_is_copied_and_verified() -> None:
    target = MemoryStore({})
    result = await migrate_content(MemoryStore({KEY: b""}), target, False)
    assert result.copied == 1
    assert result.total_bytes == 0
    assert target.objects == {KEY: b""}


@pytest.mark.asyncio
async def test_empty_listing_returns_zero_counts() -> None:
    result = await migrate_content(MemoryStore({}), MemoryStore({}), False)
    assert result.model_dump() == dict(copied=0, skipped=0, planned=0, total_bytes=0)


@pytest.mark.asyncio
async def test_failed_readback_does_not_report_success() -> None:
    source = MemoryStore({KEY: b"data"})
    target = MemoryStore({})
    target.corrupt = True
    with pytest.raises(StorageFailure, match="verification"):
        await migrate_content(source, target, False)
    assert source.closed == 2
    assert target.closed == 1


@pytest.mark.asyncio
async def test_cancelled_write_closes_source_stream() -> None:
    source = MemoryStore({KEY: b"data"})
    target = MemoryStore({})
    target.cancel = True
    with pytest.raises(asyncio.CancelledError):
        await migrate_content(source, target, False)
    assert source.closed == 2
