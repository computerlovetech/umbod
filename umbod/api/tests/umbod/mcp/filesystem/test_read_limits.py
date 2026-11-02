import asyncio
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import anyio
import pytest
from fastmcp.exceptions import ResourceError
from fastmcp.resources.base import ResourceResult

from umbod.core.callers import AuthenticationProvenance
from umbod.core.filesystem.browsing import NodeSummary
from umbod.core.filesystem.content import FilesystemContent
from umbod.core.filesystem.content.models import ContentDownload
from umbod.core.filesystem.errors import StorageFailure
from umbod.core.filesystem.models import NodeKind, NodeMetadata
from umbod.mcp.filesystem.ports import FilesystemCallerCapture, FilesystemServiceFactory
from umbod.mcp.filesystem.resources import FilesystemFileResource, MAX_READ_BYTES

from .conftest import caller_snapshot


TOO_LARGE = "filesystem_read_too_large: Filesystem file exceeds read limit. Use an authorized HTTP download instead of resources/read."
INVALID_ENCODING = "filesystem_read_invalid_encoding: File is not valid UTF-8. Use an authorized HTTP download to retrieve the original bytes."
STORAGE_FAILURE = "filesystem_storage_failure: Filesystem storage unavailable. A write may have completed; check the destination before retrying. If this persists, contact the administrator with the request ID and server version."
OPERATION_FAILED = "filesystem_operation_failed: Filesystem operation failed. A write may have completed; check the destination before retrying. If this persists, contact the administrator with the request ID and server version."


class OrdinaryByteStream:
    def __init__(self, chunks: list[bytes]) -> None:
        self.chunks = chunks
        self.failure: BaseException = StopAsyncIteration()
        self.iterations = 0
        self.read_chunks: list[bytes] = []
        self.exhausted = False

    def __aiter__(self) -> AsyncIterator[bytes]:
        self.iterations += 1
        return self

    async def __anext__(self) -> bytes:
        index = len(self.read_chunks)
        if index < len(self.chunks):
            chunk = self.chunks[index]
            self.read_chunks.append(chunk)
            return chunk
        self.exhausted = isinstance(self.failure, StopAsyncIteration)
        raise self.failure


class FakeStream(OrdinaryByteStream):
    def __init__(self, chunks: list[bytes]) -> None:
        super().__init__(chunks)
        self.close_failures: list[BaseException] = []
        self.close_count = 0

    async def aclose(self) -> None:
        self.close_count += 1
        if self.close_failures:
            raise self.close_failures.pop(0)


class AwaitingCloseStream(FakeStream):
    def __init__(self, chunks: list[bytes]) -> None:
        super().__init__(chunks)
        self.iteration_started = asyncio.Event()
        self.iteration_release = asyncio.Event()
        self.close_completed = False
        self.iteration_tasks: list[int] = []
        self.close_tasks: list[int] = []

    async def __anext__(self) -> bytes:
        self.iteration_tasks.append(anyio.get_current_task().id)
        self.iteration_started.set()
        await self.iteration_release.wait()
        return await super().__anext__()

    async def aclose(self) -> None:
        self.close_tasks.append(anyio.get_current_task().id)
        await anyio.lowlevel.checkpoint()
        await super().aclose()
        self.close_completed = True


async def cancel_scope_after_iteration_starts(
    stream: AwaitingCloseStream, scope: anyio.CancelScope,
) -> None:
    await stream.iteration_started.wait()
    scope.cancel()


class ReadHarness:
    def __init__(self) -> None:
        self.node_id = uuid4()
        now = datetime.now(timezone.utc)
        self.node = NodeSummary(
            id=self.node_id, parent_id=uuid4(), name="private.txt", kind=NodeKind.FILE,
            metadata=NodeMetadata(content_type="text/plain", attributes={}),
            created_at=now, updated_at=now, revision=7,
        )
        self.snapshot = caller_snapshot(
            "alice", "https://issuer", ("readers",), AuthenticationProvenance.UPSTREAM_VERIFIED,
        )
        self.callers = Mock(spec=FilesystemCallerCapture)
        self.callers.capture.return_value = self.snapshot
        self.services = Mock(spec=FilesystemServiceFactory)
        self.content = Mock(spec=FilesystemContent)
        self.services.content.return_value = self.content
        self.resource = FilesystemFileResource(self.node_id, self.callers, self.services)

    async def read(self, stream: AsyncIterator[bytes], size: int) -> ResourceResult:
        self.content.open_download = AsyncMock(return_value=ContentDownload(
            node=self.node, data=stream, size=size,
        ))
        return await self.resource.read()


@pytest.fixture
def harness() -> ReadHarness:
    return ReadHarness()


@pytest.mark.asyncio
@pytest.mark.parametrize("size", [0, 1, MAX_READ_BYTES])
async def test_complete_read_at_fixed_boundary(harness: ReadHarness, size: int) -> None:
    stream = FakeStream([b"a" * size])
    result = await harness.read(stream, size)
    assert result.contents[0].content == "a" * size
    assert result.contents[0].meta == {"revision": 7, "size_bytes": size}
    harness.callers.capture.assert_called_once_with()
    harness.services.content.assert_called_once_with()
    harness.content.open_download.assert_awaited_once_with(harness.snapshot, harness.node_id)
    assert stream.exhausted
    assert stream.close_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("size,message", [(MAX_READ_BYTES + 1, TOO_LARGE), (-1, STORAGE_FAILURE)])
async def test_invalid_advertised_size_closes_without_iteration(
    harness: ReadHarness, size: int, message: str,
) -> None:
    stream = FakeStream([b"secret"])
    with pytest.raises(ResourceError, match=message):
        await harness.read(stream, size)
    assert stream.iterations == 0
    assert stream.close_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("advertised", [0, MAX_READ_BYTES])
async def test_stream_overrun_never_truncates(harness: ReadHarness, advertised: int) -> None:
    stream = FakeStream([b"x" * MAX_READ_BYTES, b"x", b"unread"])
    with pytest.raises(ResourceError, match=TOO_LARGE):
        await harness.read(stream, advertised)
    assert len(stream.read_chunks) == 2
    assert not stream.exhausted
    assert stream.close_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("advertised", [0, 2, 4, 8])
async def test_eof_size_mismatch_never_returns_partial_success(
    harness: ReadHarness, advertised: int,
) -> None:
    stream = FakeStream([b"a", b"bc"])
    with pytest.raises(ResourceError, match=STORAGE_FAILURE):
        await harness.read(stream, advertised)
    assert stream.exhausted
    assert stream.close_count == 1


@pytest.mark.asyncio
async def test_split_multibyte_utf8_decodes_after_complete_read(harness: ReadHarness) -> None:
    data = "é😀終".encode()
    stream = FakeStream([data[index:index + 1] for index in range(len(data))])
    result = await harness.read(stream, len(data))
    assert result.contents[0].content == "é😀終"
    assert stream.exhausted
    assert stream.close_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("data", [b"\xffSECRET", b"\xc3", b"\xc0\xaf", b"\xed\xa0\x80"])
async def test_invalid_text_is_safe_and_cleanup_failure_preserves_rejection(
    harness: ReadHarness, data: bytes,
) -> None:
    stream = FakeStream([data])
    stream.close_failures.append(RuntimeError("SECRET"))
    with pytest.raises(ResourceError, match=INVALID_ENCODING):
        await harness.read(stream, len(data))
    assert stream.close_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("failure,message", [
    (StorageFailure("SECRET"), STORAGE_FAILURE),
    (RuntimeError("SECRET"), OPERATION_FAILED),
])
@pytest.mark.parametrize("close_fails", [False, True])
async def test_stream_failure_is_preserved_during_cleanup(
    harness: ReadHarness, failure: Exception, message: str, close_fails: bool,
) -> None:
    stream = FakeStream([b"partial"])
    stream.failure = failure
    if close_fails:
        stream.close_failures.append(RuntimeError("SECRET"))
    with pytest.raises(ResourceError, match=message):
        await harness.read(stream, 20)
    assert stream.close_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("close_fails", [False, True])
async def test_stream_cancellation_propagates_after_cleanup(harness: ReadHarness, close_fails: bool) -> None:
    stream = FakeStream([b"partial"])
    cancellation = asyncio.CancelledError()
    stream.failure = cancellation
    if close_fails:
        stream.close_failures.append(RuntimeError("SECRET"))
    with pytest.raises(asyncio.CancelledError) as error:
        await harness.read(stream, 20)
    assert error.value is cancellation
    assert stream.close_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("failure,message", [
    (RuntimeError("SECRET"), OPERATION_FAILED),
    (StorageFailure("SECRET"), STORAGE_FAILURE),
])
async def test_cleanup_failure_after_success_is_sanitized(
    harness: ReadHarness, failure: Exception, message: str,
) -> None:
    stream = FakeStream([b"ok"])
    stream.close_failures.append(failure)
    with pytest.raises(ResourceError, match=message):
        await harness.read(stream, 2)
    assert stream.close_count == 1


@pytest.mark.asyncio
async def test_ordinary_stream_without_close_is_supported(harness: ReadHarness) -> None:
    stream = OrdinaryByteStream([b"hello"])
    result = await harness.read(stream, 5)
    assert result.contents[0].content == "hello"
    assert stream.exhausted


@pytest.mark.asyncio
async def test_anyio_scope_cancellation_completes_shielded_close_in_same_task(harness: ReadHarness) -> None:
    stream = AwaitingCloseStream([b"unread"])
    with anyio.fail_after(2):
        async with anyio.create_task_group() as tasks:
            with anyio.CancelScope() as scope:
                tasks.start_soon(cancel_scope_after_iteration_starts, stream, scope)
                with pytest.raises(asyncio.CancelledError):
                    await harness.read(stream, 6)
    assert stream.close_completed
    assert stream.close_count == 1
    assert stream.close_tasks == stream.iteration_tasks


@pytest.mark.asyncio
async def test_preflight_failure_in_cancelled_scope_closes_stream(harness: ReadHarness) -> None:
    stream = AwaitingCloseStream([b"unread"])
    caller_task = anyio.get_current_task().id
    with anyio.fail_after(2):
        with anyio.CancelScope() as scope:
            scope.cancel()
            with pytest.raises(ResourceError, match=TOO_LARGE):
                await harness.read(stream, MAX_READ_BYTES + 1)
    assert stream.iterations == 0
    assert stream.close_completed
    assert stream.close_tasks == [caller_task]


@pytest.mark.asyncio
async def test_asyncio_task_cancellation_completes_shielded_close(harness: ReadHarness) -> None:
    stream = AwaitingCloseStream([b"unread"])
    with anyio.fail_after(2):
        task = asyncio.create_task(harness.read(stream, 6))
        await stream.iteration_started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert task.cancelled()
    assert stream.close_completed
    assert stream.close_tasks == stream.iteration_tasks


@pytest.mark.asyncio
async def test_cleanup_cancellation_preserves_primary_rejection(harness: ReadHarness) -> None:
    stream = FakeStream([b"unread"])
    stream.close_failures.append(asyncio.CancelledError())
    with pytest.raises(ResourceError, match=TOO_LARGE):
        await harness.read(stream, MAX_READ_BYTES + 1)
    assert stream.close_count == 1
