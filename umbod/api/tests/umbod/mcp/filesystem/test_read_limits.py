import asyncio
import base64
import json
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import anyio
import pytest
from fastmcp.exceptions import ToolError
from fastmcp.tools.base import ToolResult

from umbod.core.callers import AuthenticationProvenance
from umbod.core.filesystem.browsing import NodeSummary
from umbod.core.filesystem.content import FilesystemContent
from umbod.core.filesystem.content.models import ContentDownload
from umbod.core.filesystem.errors import StorageFailure
from umbod.core.filesystem.models import NodeKind, NodeMetadata
from umbod.mcp.filesystem.ports import FilesystemCallerCapture, FilesystemServiceFactory
from umbod.mcp.filesystem.read import FilesystemReadFileTool
from umbod.mcp.filesystem.read_models import MAX_READ_BYTES

from .conftest import caller_snapshot


TOO_LARGE = "filesystem_read_too_large: Filesystem file exceeds read limit"
INVALID_ENCODING = "filesystem_read_invalid_encoding: File is not valid UTF-8; use base64"
STORAGE_FAILURE = "filesystem_storage_failure: Filesystem storage unavailable"
OPERATION_FAILED = "filesystem_operation_failed: Filesystem operation failed"


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
        self.tool = FilesystemReadFileTool(self.callers, self.services)

    async def read(
        self, stream: AsyncIterator[bytes], size: int, limit: int,
        encoding: str,
    ) -> ToolResult:
        self.content.open_download = AsyncMock(return_value=ContentDownload(
            node=self.node, data=stream, size=size,
        ))
        arguments: dict[str, Any] = {
            "node_id": str(self.node_id), "encoding": encoding, "max_bytes": limit,
        }
        return await self.tool.run(arguments)


@pytest.fixture
def harness() -> ReadHarness:
    return ReadHarness()


@pytest.mark.asyncio
async def test_success_uses_one_captured_download_and_json_fallback(harness: ReadHarness) -> None:
    stream = FakeStream([b"hello"])
    result = await harness.read(stream, 5, 5, "utf-8")
    expected = {
        "node_id": str(harness.node_id), "revision": 7, "size_bytes": 5,
        "content": {"encoding": "utf-8", "text": "hello"},
    }
    assert result.structured_content == expected
    assert json.loads(result.content[0].text) == expected
    harness.callers.capture.assert_called_once_with()
    harness.services.content.assert_called_once_with()
    harness.content.open_download.assert_awaited_once_with(harness.snapshot, harness.node_id)
    assert stream.close_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("size,limit", [(1, 0), (4, 3), (MAX_READ_BYTES + 1, MAX_READ_BYTES)])
async def test_advertised_oversize_closes_without_iteration(
    harness: ReadHarness, size: int, limit: int,
) -> None:
    stream = FakeStream([b"secret"])
    with pytest.raises(ToolError) as error:
        await harness.read(stream, size, limit, "utf-8")
    assert str(error.value) == TOO_LARGE
    assert stream.iterations == 0
    assert stream.read_chunks == []
    assert stream.close_count == 1


@pytest.mark.asyncio
async def test_negative_advertised_size_closes_without_iteration(harness: ReadHarness) -> None:
    stream = FakeStream([b"secret"])
    with pytest.raises(ToolError) as error:
        await harness.read(stream, -1, 10, "utf-8")
    assert str(error.value) == STORAGE_FAILURE
    assert stream.iterations == 0
    assert stream.close_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("advertised", [0, 2, 3])
async def test_actual_overrun_stops_at_first_exceeding_chunk(
    harness: ReadHarness, advertised: int,
) -> None:
    stream = FakeStream([b"\xff\xff", b"xx", b"unread secret"])
    with pytest.raises(ToolError) as error:
        await harness.read(stream, advertised, 3, "utf-8")
    assert str(error.value) == TOO_LARGE
    assert stream.read_chunks == [b"\xff\xff", b"xx"]
    assert not stream.exhausted
    assert stream.close_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("advertised", [0, 2, 4, 8])
async def test_eof_size_mismatch_never_returns_partial_success(
    harness: ReadHarness, advertised: int,
) -> None:
    stream = FakeStream([b"a", b"bc"])
    with pytest.raises(ToolError) as error:
        await harness.read(stream, advertised, 8, "utf-8")
    assert str(error.value) == STORAGE_FAILURE
    assert stream.exhausted
    assert stream.close_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("size", [0, 1, MAX_READ_BYTES])
async def test_exact_caller_limit_including_zero_and_global_boundary_succeeds(
    harness: ReadHarness, size: int,
) -> None:
    stream = FakeStream([b"a" * size])
    result = await harness.read(stream, size, size, "utf-8")
    assert result.structured_content == {
        "node_id": str(harness.node_id), "revision": 7, "size_bytes": size,
        "content": {"encoding": "utf-8", "text": "a" * size},
    }
    assert stream.exhausted
    assert stream.close_count == 1


@pytest.mark.asyncio
async def test_zero_limit_rejects_first_unadvertised_byte(harness: ReadHarness) -> None:
    stream = FakeStream([b"", b"x", b"unread"])
    with pytest.raises(ToolError) as error:
        await harness.read(stream, 0, 0, "utf-8")
    assert str(error.value) == TOO_LARGE
    assert stream.read_chunks == [b"", b"x"]
    assert stream.close_count == 1


@pytest.mark.asyncio
async def test_utf8_decodes_only_after_all_split_multibyte_chunks(harness: ReadHarness) -> None:
    data = "é😀終".encode("utf-8")
    stream = FakeStream([data[index:index + 1] for index in range(len(data))])
    result = await harness.read(stream, len(data), len(data), "utf-8")
    assert result.structured_content["content"] == {"encoding": "utf-8", "text": "é😀終"}
    assert stream.exhausted
    assert stream.close_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("data", [b"\xffSECRET", b"\xc3", b"\xc0\xaf", b"\xed\xa0\x80"])
async def test_invalid_utf8_is_sanitized_after_complete_read(
    harness: ReadHarness, data: bytes,
) -> None:
    stream = FakeStream([data, b""])
    with pytest.raises(ToolError) as error:
        await harness.read(stream, len(data), len(data), "utf-8")
    assert str(error.value) == INVALID_ENCODING
    assert stream.exhausted
    assert stream.close_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("chunks", [[b"\xff", b"\x00\xfe", b"\x80"], [b"a", b"bc", b"de"], []])
async def test_base64_encodes_complete_binary_in_canonical_form(
    harness: ReadHarness, chunks: list[bytes],
) -> None:
    data = b"".join(chunks)
    stream = FakeStream(chunks)
    result = await harness.read(stream, len(data), len(data), "base64")
    assert result.structured_content["content"] == {
        "encoding": "base64", "data": base64.b64encode(data).decode("ascii"),
    }
    assert stream.exhausted
    assert stream.close_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("failure,message", [
    (StorageFailure("SECRET storage location"), STORAGE_FAILURE),
    (RuntimeError("SECRET storage location"), OPERATION_FAILED),
])
@pytest.mark.parametrize("close_fails", [False, True])
async def test_stream_failure_is_preserved_when_cleanup_also_fails(
    harness: ReadHarness, failure: Exception, message: str, close_fails: bool,
) -> None:
    stream = FakeStream([b"partial"])
    stream.failure = failure
    if close_fails:
        stream.close_failures.append(RuntimeError("SECRET cleanup path"))
    with pytest.raises(ToolError) as error:
        await harness.read(stream, 20, 20, "utf-8")
    assert str(error.value) == message
    assert stream.close_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("close_fails", [False, True])
async def test_stream_cancellation_propagates_after_cleanup(
    harness: ReadHarness, close_fails: bool,
) -> None:
    cancellation = asyncio.CancelledError("cancelled read")
    stream = FakeStream([b"partial"])
    stream.failure = cancellation
    if close_fails:
        stream.close_failures.append(RuntimeError("SECRET cleanup path"))
    with pytest.raises(asyncio.CancelledError) as error:
        await harness.read(stream, 20, 20, "utf-8")
    assert error.value is cancellation
    assert stream.close_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("size,limit,chunks,message", [
    (4, 3, [b"unread"], TOO_LARGE),
    (0, 1, [b"xx"], TOO_LARGE),
    (-1, 3, [], STORAGE_FAILURE),
    (2, 3, [b"x"], STORAGE_FAILURE),
    (1, 1, [b"\xff"], INVALID_ENCODING),
])
async def test_cleanup_failure_does_not_replace_read_rejection(
    harness: ReadHarness, size: int, limit: int, chunks: list[bytes], message: str,
) -> None:
    stream = FakeStream(chunks)
    stream.close_failures.append(RuntimeError("SECRET cleanup path"))
    with pytest.raises(ToolError) as error:
        await harness.read(stream, size, limit, "utf-8")
    assert str(error.value) == message
    assert stream.close_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("failure,message", [
    (RuntimeError("SECRET cleanup path"), OPERATION_FAILED),
    (StorageFailure("SECRET cleanup path"), STORAGE_FAILURE),
])
async def test_cleanup_failure_after_success_surfaces_sanitized_error(
    harness: ReadHarness, failure: Exception, message: str,
) -> None:
    stream = FakeStream([b"ok"])
    stream.close_failures.append(failure)
    with pytest.raises(ToolError) as error:
        await harness.read(stream, 2, 2, "utf-8")
    assert str(error.value) == message
    assert stream.close_count == 1


@pytest.mark.asyncio
async def test_ordinary_byte_stream_without_close_is_supported(harness: ReadHarness) -> None:
    stream = OrdinaryByteStream([b"hello"])
    result = await harness.read(stream, 5, 5, "utf-8")
    assert result.structured_content["content"] == {"encoding": "utf-8", "text": "hello"}
    assert stream.exhausted


@pytest.mark.asyncio
async def test_anyio_scope_cancellation_completes_awaiting_close_in_same_task(
    harness: ReadHarness,
) -> None:
    stream = AwaitingCloseStream([b"unread"])
    with anyio.fail_after(2):
        async with anyio.create_task_group() as tasks:
            with anyio.CancelScope() as scope:
                tasks.start_soon(cancel_scope_after_iteration_starts, stream, scope)
                with pytest.raises(asyncio.CancelledError):
                    await harness.read(stream, 6, 6, "utf-8")
    assert stream.iteration_started.is_set()
    assert stream.read_chunks == []
    assert stream.close_count == 1
    assert stream.close_completed
    assert stream.close_tasks == stream.iteration_tasks


@pytest.mark.asyncio
async def test_preflight_oversize_in_cancelled_scope_completes_awaiting_close(
    harness: ReadHarness,
) -> None:
    stream = AwaitingCloseStream([b"unread"])
    caller_task = anyio.get_current_task().id
    with anyio.fail_after(2):
        with anyio.CancelScope() as scope:
            scope.cancel()
            with pytest.raises(ToolError) as error:
                await harness.read(stream, 6, 5, "utf-8")
    assert str(error.value) == TOO_LARGE
    assert stream.iterations == 0
    assert not stream.iteration_started.is_set()
    assert stream.close_count == 1
    assert stream.close_completed
    assert stream.close_tasks == [caller_task]


@pytest.mark.asyncio
async def test_asyncio_task_cancellation_completes_awaiting_close(
    harness: ReadHarness,
) -> None:
    stream = AwaitingCloseStream([b"unread"])
    with anyio.fail_after(2):
        task = asyncio.create_task(harness.read(stream, 6, 6, "utf-8"))
        try:
            await stream.iteration_started.wait()
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        finally:
            if not task.done():
                task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await task
    assert task.cancelled()
    assert stream.read_chunks == []
    assert stream.close_count == 1
    assert stream.close_completed
    assert stream.close_tasks == stream.iteration_tasks


@pytest.mark.asyncio
async def test_cleanup_cancelled_error_preserves_primary_read_too_large(
    harness: ReadHarness,
) -> None:
    stream = FakeStream([b"unread"])
    stream.close_failures.append(asyncio.CancelledError("SECRET cleanup cancellation"))
    with pytest.raises(ToolError) as error:
        await harness.read(stream, 6, 5, "utf-8")
    assert str(error.value) == TOO_LARGE
    assert stream.iterations == 0
    assert stream.close_count == 1
