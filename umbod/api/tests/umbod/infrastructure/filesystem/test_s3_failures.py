import asyncio
from collections.abc import AsyncIterator
from typing import cast

import pytest

from tests.umbod.infrastructure.filesystem.test_s3_content import (
    FakeBackend,
    chunks,
    collect,
    configuration,
)
from umbod.core.filesystem import ContentDriver, StorageFailure
from umbod.core.filesystem.content.errors import UploadTooLarge
from umbod.core.filesystem.uploads.errors import UploadLengthMismatch
from umbod.infrastructure.filesystem.s3_content import S3Content


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["get", "read"])
async def test_read_sdk_failure_sanitizes_error_and_closes_resources(failure: str) -> None:
    backend = FakeBackend()
    content: ContentDriver = S3Content(configuration(), backend.provider)
    reference = await content.put(chunks(b"data"))
    backend.failure = failure
    with pytest.raises(StorageFailure) as error:
        await collect(content.get(reference.key))
    assert str(error.value) == "Cannot read content object"
    assert backend.active == 0
    assert all(body.closed for body in backend.bodies)


@pytest.mark.asyncio
async def test_missing_object_uses_sanitized_storage_failure() -> None:
    backend = FakeBackend()
    content: ContentDriver = S3Content(configuration(), backend.provider)
    with pytest.raises(StorageFailure, match="Cannot read content object"):
        await collect(content.get("a" * 32))
    assert backend.active == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("invalid", ["text", 1, None, bytearray(b"x")])
async def test_invalid_small_input_fails_without_any_object_write(invalid: object) -> None:
    backend = FakeBackend()
    content: ContentDriver = S3Content(configuration(), backend.provider)

    async def invalid_stream() -> AsyncIterator[bytes]:
        yield cast(bytes, invalid)

    with pytest.raises(StorageFailure):
        await content.put(invalid_stream())
    assert not backend.objects
    assert not backend.uploads
    assert not backend.calls
    assert backend.active == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("failure_type", [UploadLengthMismatch, UploadTooLarge, RuntimeError])
@pytest.mark.parametrize("multipart", [False, True])
async def test_source_validation_errors_preserve_identity_after_storage_cleanup(
    monkeypatch: pytest.MonkeyPatch, failure_type: type[Exception], multipart: bool,
) -> None:
    monkeypatch.setattr("umbod.infrastructure.filesystem.s3_content.PART_SIZE", 8)
    backend = FakeBackend()
    content: ContentDriver = S3Content(configuration(), backend.provider)
    failure = failure_type("input validation failed")

    async def rejected_stream() -> AsyncIterator[bytes]:
        yield b"x" * (17 if multipart else 1)
        raise failure

    with pytest.raises(failure_type) as caught:
        await content.put(rejected_stream())

    assert caught.value is failure
    assert not backend.objects
    assert not backend.uploads
    assert backend.aborts == int(multipart)
    assert backend.active == 0


@pytest.mark.asyncio
async def test_cancelled_input_after_multipart_started_aborts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("umbod.infrastructure.filesystem.s3_content.PART_SIZE", 8)
    backend = FakeBackend()
    content: ContentDriver = S3Content(configuration(), backend.provider)

    async def cancelled_stream() -> AsyncIterator[bytes]:
        yield b"x" * 17
        raise asyncio.CancelledError()

    with pytest.raises(asyncio.CancelledError):
        await content.put(cancelled_stream())
    assert not backend.objects
    assert not backend.uploads
    assert backend.aborts == 1
    assert backend.active == 0


@pytest.mark.asyncio
async def test_repeated_cancellation_during_abort_finishes_cleanup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("umbod.infrastructure.filesystem.s3_content.PART_SIZE", 8)
    backend = FakeBackend()
    backend.block = "abort"
    backend.failure = "upload"
    content: ContentDriver = S3Content(configuration(), backend.provider)
    task = asyncio.create_task(content.put(chunks(b"x" * 19)))
    await asyncio.wait_for(backend.entered.wait(), 2)
    task.cancel()
    await asyncio.sleep(0)
    task.cancel()
    backend.release.set()
    with pytest.raises(StorageFailure):
        await asyncio.wait_for(task, 2)
    assert not backend.uploads
    assert backend.active == 0


@pytest.mark.asyncio
async def test_cancellation_during_context_exit_settles_before_returning() -> None:
    backend = FakeBackend()
    backend.block = "exit"
    content: ContentDriver = S3Content(configuration(), backend.provider)
    task = asyncio.create_task(content.put(chunks(b"data")))
    await asyncio.wait_for(backend.entered.wait(), 2)
    task.cancel()
    await asyncio.sleep(0)
    task.cancel()
    backend.release.set()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(task, 2)
    assert backend.active == 0
