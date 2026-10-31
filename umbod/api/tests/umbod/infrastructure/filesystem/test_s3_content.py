import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import cast
from uuid import UUID

import pytest

from umbod.core.filesystem import ByteStream, ContentDriver, StorageFailure
from umbod.infrastructure import S3ContentConfig
from umbod.infrastructure.filesystem.s3.edge import S3Client
from umbod.infrastructure.filesystem.s3_content import S3Content


def configuration() -> S3ContentConfig:
    return S3ContentConfig(
        type="s3", bucket="test-bucket", region="us-east-1",
        endpoint_url="", prefix="", addressing_style="auto",
    )


async def chunks(*values: bytes) -> AsyncIterator[bytes]:
    for value in values:
        yield value


async def collect(stream: ByteStream) -> bytes:
    return b"".join([chunk async for chunk in stream])


class FakeBody:
    def __init__(self, backend: "FakeBackend", data: bytes) -> None:
        self.backend = backend
        self.data = data
        self.offset = 0
        self.closed = False
        self.read_sizes: list[int] = []

    async def read(self, amount: int) -> bytes:
        await self.backend.step("read")
        self.read_sizes.append(amount)
        result = self.data[self.offset:self.offset + amount]
        self.offset += len(result)
        return result

    def close(self) -> None:
        self.closed = True


class FakeBackend:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.uploads: dict[str, dict[int, bytes]] = {}
        self.calls: list[tuple[str, dict[str, object]]] = []
        self.bodies: list[FakeBody] = []
        self.active = 0
        self.opens = 0
        self.aborts = 0
        self.block = ""
        self.failure = ""
        self.malformed = ""
        self.length_adjustment = 0
        self.entered = asyncio.Event()
        self.release = asyncio.Event()

    async def step(self, name: str) -> None:
        if name == self.block:
            self.entered.set()
            await self.release.wait()
        if name == self.failure:
            raise RuntimeError("secret endpoint bucket key SDK details")

    @asynccontextmanager
    async def provider(self) -> AsyncIterator[S3Client]:
        self.opens += 1
        self.active += 1
        try:
            await self.step("enter")
            yield cast(S3Client, FakeClient(self))
        finally:
            await self.step("exit")
            self.active -= 1


class FakeClient:
    def __init__(self, backend: FakeBackend) -> None:
        self.backend = backend

    async def _call(self, name: str, arguments: dict[str, object]) -> None:
        self.backend.calls.append((name, arguments))
        await self.backend.step(name)

    async def put_object(self, **kwargs: object) -> object:
        await self._call("put", kwargs)
        key = cast(str, kwargs["Key"])
        assert kwargs["IfNoneMatch"] == "*"
        if key in self.backend.objects:
            raise RuntimeError("collision")
        self.backend.objects[key] = cast(bytes, kwargs["Body"])
        return {} if self.backend.malformed == "put" else {"ETag": "tag"}

    async def create_multipart_upload(self, **kwargs: object) -> object:
        await self._call("create", kwargs)
        upload_id = str(len(self.backend.calls))
        self.backend.uploads[upload_id] = {}
        return {"UploadId": upload_id}

    async def upload_part(self, **kwargs: object) -> object:
        await self._call("upload", kwargs)
        upload_id = cast(str, kwargs["UploadId"])
        number = cast(int, kwargs["PartNumber"])
        self.backend.uploads[upload_id][number] = cast(bytes, kwargs["Body"])
        return {} if self.backend.malformed == "upload" else {"ETag": str(number)}

    async def complete_multipart_upload(self, **kwargs: object) -> object:
        await self._call("complete", kwargs)
        assert kwargs["IfNoneMatch"] == "*"
        key = cast(str, kwargs["Key"])
        if key in self.backend.objects:
            raise RuntimeError("collision")
        upload_id = cast(str, kwargs["UploadId"])
        parts = self.backend.uploads.pop(upload_id)
        self.backend.objects[key] = b"".join(parts[index] for index in sorted(parts))
        return {} if self.backend.malformed == "complete" else {"ETag": "tag"}

    async def abort_multipart_upload(self, **kwargs: object) -> object:
        self.backend.aborts += 1
        await self._call("abort", kwargs)
        self.backend.uploads.pop(cast(str, kwargs["UploadId"]), None)
        return {}

    async def get_object(self, **kwargs: object) -> object:
        await self._call("get", kwargs)
        data = self.backend.objects[cast(str, kwargs["Key"])]
        body = FakeBody(self.backend, data)
        self.backend.bodies.append(body)
        if self.backend.malformed == "metadata":
            return {"Body": body, "ContentLength": "invalid"}
        return {"Body": body, "ContentLength": len(data) + self.backend.length_adjustment}


@pytest.fixture
def backend() -> FakeBackend:
    return FakeBackend()


@pytest.fixture
def content(backend: FakeBackend) -> ContentDriver:
    return S3Content(configuration(), backend.provider)


@pytest.fixture
def small_parts(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("umbod.infrastructure.filesystem.s3_content.PART_SIZE", 8)


@pytest.mark.asyncio
@pytest.mark.parametrize("values", [(), (b"",), (b"binary\x00\xff",), (b"a", b"", b"bc", b"def")])
async def test_roundtrip_exact_size_with_fresh_driver(
    backend: FakeBackend, content: ContentDriver, values: tuple[bytes, ...],
) -> None:
    reference = await content.put(chunks(*values))
    reopened: ContentDriver = S3Content(configuration(), backend.provider)
    assert await collect(reopened.get(reference.key)) == b"".join(values)
    assert reference.size == sum(map(len, values))
    assert UUID(reference.key).hex == reference.key
    assert backend.active == 0
    assert all(body.closed for body in backend.bodies)


@pytest.mark.asyncio
async def test_independent_writes_publish_distinct_immutable_keys(
    content: ContentDriver,
) -> None:
    first, second = await asyncio.gather(content.put(chunks(b"first")), content.put(chunks(b"second")))
    assert first.key != second.key
    assert await collect(content.get(first.key)) == b"first"
    assert await collect(content.get(second.key)) == b"second"


@pytest.mark.asyncio
@pytest.mark.parametrize("size", [0, 8, 9, 16, 29])
async def test_streaming_part_bounds_and_partial_last_part(
    backend: FakeBackend, content: ContentDriver, small_parts: None, size: int,
) -> None:
    data = bytes(range(size))
    reference = await content.put(chunks(data[:3], data[3:7], data[7:]))
    assert reference.size == size
    assert await collect(content.get(reference.key)) == data
    writes = [(name, call) for name, call in backend.calls if name in ("put", "upload")]
    assert all(len(cast(bytes, call["Body"])) <= 8 for _, call in writes)
    assert [len(cast(bytes, call["Body"])) for _, call in writes] == (
        [size] if size <= 8 else [8] * (size // 8) + ([size % 8] if size % 8 else [])
    )
    assert not backend.uploads


@pytest.mark.asyncio
async def test_real_part_size_accepts_large_single_chunk(
    backend: FakeBackend, content: ContentDriver,
) -> None:
    data = b"x" * (17 * 1024 * 1024 + 3)
    reference = await content.put(chunks(data))
    assert backend.objects[reference.key] == data
    sizes = [len(cast(bytes, call["Body"])) for name, call in backend.calls if name == "upload"]
    assert sizes == [8 * 1024 * 1024, 8 * 1024 * 1024, 1024 * 1024 + 3]


@pytest.mark.asyncio
@pytest.mark.parametrize("data", [b"old", b"x" * 19])
async def test_conditional_collision_never_overwrites_existing_object(
    backend: FakeBackend, small_parts: None, monkeypatch: pytest.MonkeyPatch, data: bytes,
) -> None:
    monkeypatch.setattr("umbod.infrastructure.filesystem.s3_content.uuid4", lambda: UUID(int=1))
    content: ContentDriver = S3Content(configuration(), backend.provider)
    first = await content.put(chunks(b"original"))
    with pytest.raises(StorageFailure, match="Cannot store content object"):
        await content.put(chunks(data))
    assert await collect(content.get(first.key)) == b"original"
    assert not backend.uploads
    assert backend.aborts == (1 if len(data) > 8 else 0)


@pytest.mark.asyncio
async def test_prefix_isolation_keeps_persisted_keys_logical(backend: FakeBackend) -> None:
    first: ContentDriver = S3Content(configuration().model_copy(update={"prefix": "first/nested"}), backend.provider)
    second: ContentDriver = S3Content(configuration().model_copy(update={"prefix": "second"}), backend.provider)
    reference = await first.put(chunks(b"isolated"))
    assert list(backend.objects) == [f"first/nested/{reference.key}"]
    with pytest.raises(StorageFailure, match="Cannot read content object"):
        await collect(second.get(reference.key))


@pytest.mark.asyncio
@pytest.mark.parametrize("key", ["", "../secret", "a/b", "A" * 32, "0" * 31, "0" * 32 + "\n"])
async def test_invalid_key_is_rejected_before_client_access(
    backend: FakeBackend, content: ContentDriver, key: str,
) -> None:
    with pytest.raises(StorageFailure, match="Invalid content key"):
        await collect(content.get(key))
    assert backend.opens == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["upload", "complete"])
async def test_sdk_failure_aborts_multipart_and_sanitizes_errors(
    backend: FakeBackend, content: ContentDriver, small_parts: None, failure: str,
) -> None:
    backend.failure = failure
    with pytest.raises(StorageFailure) as error:
        await content.put(chunks(b"x" * 25))
    assert str(error.value) == "Cannot store content object"
    assert backend.aborts == 1
    assert not backend.uploads
    assert not backend.objects
    assert backend.active == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("invalid_chunk", [True, False])
async def test_input_failure_after_multipart_started_aborts(
    backend: FakeBackend, content: ContentDriver, small_parts: None, invalid_chunk: bool,
) -> None:
    async def failing() -> AsyncIterator[bytes]:
        yield b"x" * 17
        if invalid_chunk:
            yield cast(bytes, "not bytes")
        else:
            raise RuntimeError("input failed")

    with pytest.raises(StorageFailure if invalid_chunk else RuntimeError):
        await content.put(failing())
    assert backend.aborts == 1
    assert not backend.uploads
    assert not backend.objects


@pytest.mark.asyncio
async def test_part_limit_aborts_without_publishing(
    backend: FakeBackend, content: ContentDriver, small_parts: None, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("umbod.infrastructure.filesystem.s3_content.MAX_PARTS", 2)
    with pytest.raises(StorageFailure):
        await content.put(chunks(b"x" * 17))
    assert backend.aborts == 1
    assert not backend.uploads
    assert not backend.objects


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["enter", "create", "upload", "complete", "put"])
async def test_cancelled_write_settles_remote_operation_and_closes_client(
    backend: FakeBackend, content: ContentDriver, small_parts: None, operation: str,
) -> None:
    backend.block = operation
    task = asyncio.create_task(content.put(chunks(b"x" * (3 if operation == "put" else 19))))
    await asyncio.wait_for(backend.entered.wait(), 2)
    task.cancel()
    await asyncio.sleep(0)
    task.cancel()
    await asyncio.sleep(0)
    assert not task.done()
    backend.release.set()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(task, 2)
    assert backend.active == 0
    assert not backend.uploads
    assert backend.aborts == (1 if operation in ("create", "upload", "complete") else 0)


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["get", "read"])
async def test_cancelled_read_closes_response_body_and_client(
    backend: FakeBackend, content: ContentDriver, operation: str,
) -> None:
    reference = await content.put(chunks(b"read me"))
    backend.block = operation
    task = asyncio.create_task(collect(content.get(reference.key)))
    await asyncio.wait_for(backend.entered.wait(), 2)
    task.cancel()
    await asyncio.sleep(0)
    task.cancel()
    backend.release.set()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(task, 2)
    assert backend.active == 0
    assert all(body.closed for body in backend.bodies)


@pytest.mark.asyncio
async def test_early_iterator_close_closes_body_before_client(
    backend: FakeBackend, content: ContentDriver,
) -> None:
    reference = await content.put(chunks(b"x" * 150000))
    stream = content.get(reference.key)
    assert len(await anext(stream)) == 65536
    await stream.aclose()
    assert backend.bodies[0].closed
    assert backend.active == 0
    assert backend.bodies[0].read_sizes == [65536]


@pytest.mark.asyncio
@pytest.mark.parametrize("adjustment", [-1, 1])
async def test_truncated_or_excess_stream_fails_and_closes_body(
    backend: FakeBackend, content: ContentDriver, adjustment: int,
) -> None:
    reference = await content.put(chunks(b"data"))
    backend.length_adjustment = adjustment
    with pytest.raises(StorageFailure, match="Cannot read content object"):
        await collect(content.get(reference.key))
    assert backend.bodies[0].closed
    assert backend.active == 0


@pytest.mark.asyncio
async def test_malformed_metadata_closes_body(
    backend: FakeBackend, content: ContentDriver,
) -> None:
    reference = await content.put(chunks(b"data"))
    backend.malformed = "metadata"
    with pytest.raises(StorageFailure):
        await collect(content.get(reference.key))
    assert backend.bodies[0].closed
    assert backend.active == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["put", "upload", "complete"])
async def test_malformed_write_response_is_not_published_as_reference(
    backend: FakeBackend, content: ContentDriver, small_parts: None, operation: str,
) -> None:
    backend.malformed = operation
    with pytest.raises(StorageFailure):
        await content.put(chunks(b"x" * (3 if operation == "put" else 19)))
    assert not backend.uploads
    assert backend.active == 0


@pytest.mark.asyncio
async def test_abort_failure_preserves_cancelled_error_and_closes_client(
    backend: FakeBackend, content: ContentDriver, small_parts: None,
) -> None:
    backend.block = "upload"
    backend.failure = "abort"
    task = asyncio.create_task(content.put(chunks(b"x" * 19)))
    await asyncio.wait_for(backend.entered.wait(), 2)
    task.cancel()
    backend.release.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert backend.aborts == 1
    assert backend.active == 0
