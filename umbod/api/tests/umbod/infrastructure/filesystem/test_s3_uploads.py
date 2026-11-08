import asyncio
import hashlib
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import cast
from urllib.parse import parse_qs, urlsplit

import pytest

from umbod.core.filesystem import StorageFailure
from botocore.exceptions import ClientError
from umbod.core.filesystem.uploads.errors import UploadConflict, UploadLengthMismatch, UploadMediaTypeMismatch
from umbod.core.filesystem.uploads.models import ExternalTransfer, ExternalTransferRequest
from umbod.infrastructure.filesystem.s3.edge import S3Client, SDKClientProvider
from umbod.infrastructure.filesystem.s3.uploads import S3UploadTransfer
from tests.umbod.infrastructure.filesystem.test_s3_content import FakeBackend, FakeClient, configuration


class TransferClient(FakeClient):
    def __init__(self, backend: FakeBackend, content_type: str, signed_headers: str) -> None:
        super().__init__(backend)
        self.content_type = content_type
        self.signed_headers = signed_headers

    async def generate_presigned_url(self, operation: str, **kwargs: object) -> str:
        await self._call(operation, kwargs)
        return "https://storage.example.test/bucket/object?X-Amz-SignedHeaders=" + self.signed_headers

    async def get_object(self, **kwargs: object) -> object:
        if self.backend.failure.startswith("sdk:"):
            raise ClientError({"Error": {"Code": self.backend.failure[4:], "Message": "secret storage URL"}}, "GetObject")
        response = cast(dict[str, object], await super().get_object(**kwargs))
        response["ContentType"] = self.content_type
        response["ETag"] = "not-a-sha256"
        return response


class TransferBackend(FakeBackend):
    def __init__(self) -> None:
        super().__init__()
        self.content_type = "application/octet-stream"
        self.signed_headers = "content-length;content-type;host;if-none-match"

    @asynccontextmanager
    async def provider(self) -> AsyncIterator[S3Client]:
        yield cast(S3Client, TransferClient(self, self.content_type, self.signed_headers))


def transfer_request(size: int = 3) -> ExternalTransferRequest:
    return ExternalTransferRequest(
        transfer=ExternalTransfer(storage_key="a" * 32, expires_at=datetime.now(timezone.utc) + timedelta(minutes=15)),
        size_bytes=size, content_type="application/octet-stream",
    )


@pytest.mark.asyncio
async def test_sdk_signs_conditional_exact_length_put_with_prefix_and_no_browser_length_header(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing-access-key")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing-secret-key")
    monkeypatch.setenv("AWS_SESSION_TOKEN", "testing-session-token")
    config = configuration().model_copy(update={
        "endpoint_url": "https://storage.example.test", "prefix": "private/nested", "addressing_style": "path",
    })
    instructions = await S3UploadTransfer(config, SDKClientProvider(config)).prepare_transfer(transfer_request())
    parsed = urlsplit(instructions.url)
    query = parse_qs(parsed.query)
    assert parsed.path == "/test-bucket/private/nested/" + "a" * 32
    assert set(query["X-Amz-SignedHeaders"][0].split(";")) == {"host", "content-length", "content-type", "if-none-match"}
    assert 0 < int(query["X-Amz-Expires"][0]) <= 900
    assert query["X-Amz-Security-Token"] == ["testing-session-token"]
    assert instructions.headers == {"Content-Type": "application/octet-stream", "If-None-Match": "*"}
    assert "testing" not in repr(instructions)
    assert "Authorization" not in instructions.headers


@pytest.mark.asyncio
async def test_presign_parameters_are_server_owned_and_fixed() -> None:
    backend = TransferBackend()
    config = configuration().model_copy(update={"prefix": "private"})
    request = transfer_request()
    await S3UploadTransfer(config, backend.provider).prepare_transfer(request)
    operation, arguments = backend.calls[0]
    assert operation == "put_object"
    assert arguments["Params"] == {
        "Bucket": "test-bucket", "Key": "private/" + "a" * 32,
        "ContentType": "application/octet-stream", "ContentLength": 3, "IfNoneMatch": "*",
    }
    assert arguments["HttpMethod"] == "PUT"
    assert 0 < arguments["ExpiresIn"] <= 900


@pytest.mark.asyncio
@pytest.mark.parametrize("headers", ["host", "host;content-type;if-none-match", "host;content-type;content-length"])
async def test_incompatible_signatures_fail_closed(headers: str) -> None:
    backend = TransferBackend()
    backend.signed_headers = headers
    with pytest.raises(StorageFailure, match="Cannot prepare upload transfer"):
        await S3UploadTransfer(configuration(), backend.provider).prepare_transfer(transfer_request())


@pytest.mark.asyncio
@pytest.mark.parametrize("size", [0, 3, 150000])
async def test_readback_hashes_actual_bytes_with_bounded_reads_and_closes(size: int) -> None:
    backend = TransferBackend()
    data = b"x" * size
    backend.objects["a" * 32] = data
    result = await S3UploadTransfer(configuration(), backend.provider).verify_transfer(transfer_request(size))
    assert result.content.key == "a" * 32
    assert result.receipt.sha256 == hashlib.sha256(data).hexdigest()
    assert result.receipt.size_bytes == size
    assert all(body.closed for body in backend.bodies)
    assert all(0 < amount <= 65536 for body in backend.bodies for amount in body.read_sizes)


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["missing", "short", "long", "type", "metadata", "read"])
async def test_failed_verification_is_sanitized_and_closes_response(failure: str) -> None:
    backend = TransferBackend()
    if failure != "missing":
        backend.objects["a" * 32] = b"abc"
    if failure in ("short", "long"):
        backend.length_adjustment = -1 if failure == "short" else 1
    if failure == "type":
        backend.content_type = "text/plain"
    if failure == "metadata":
        backend.malformed = "metadata"
    if failure == "read":
        backend.failure = "read"
    error = UploadLengthMismatch if failure in ("short", "long") else UploadMediaTypeMismatch if failure == "type" else StorageFailure
    with pytest.raises(error) as caught:
        await S3UploadTransfer(configuration(), backend.provider).verify_transfer(transfer_request())
    assert "secret" not in str(caught.value)
    assert "bucket" not in str(caught.value)
    assert all(body.closed for body in backend.bodies)


@pytest.mark.asyncio
async def test_cancelled_verification_closes_response() -> None:
    backend = TransferBackend()
    backend.objects["a" * 32] = b"abc"
    backend.block = "read"
    task = asyncio.create_task(S3UploadTransfer(configuration(), backend.provider).verify_transfer(transfer_request()))
    await asyncio.wait_for(backend.entered.wait(), 2)
    task.cancel()
    backend.release.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert all(body.closed for body in backend.bodies)


@pytest.mark.asyncio
@pytest.mark.parametrize("expired", [False, True])
async def test_admission_rejects_storage_cap_and_expired_deadline_without_sdk(expired: bool) -> None:
    backend = TransferBackend()
    request = transfer_request(5 * 1024 ** 3 + 1)
    if expired:
        request = transfer_request().model_copy(update={
            "transfer": ExternalTransfer(storage_key="a" * 32, expires_at=datetime.now(timezone.utc) - timedelta(seconds=1)),
        })
    with pytest.raises(StorageFailure):
        await S3UploadTransfer(configuration(), backend.provider).prepare_transfer(request)
    assert backend.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize("code", ["NoSuchKey", "404", "AccessDenied", "403", "SlowDown"])
async def test_only_missing_object_errors_map_to_pending_conflict(code: str) -> None:
    backend = TransferBackend()
    backend.failure = "sdk:" + code
    expected = UploadConflict if code in ("NoSuchKey", "404") else StorageFailure
    with pytest.raises(expected) as error:
        await S3UploadTransfer(configuration(), backend.provider).verify_transfer(transfer_request())
    assert "secret" not in str(error.value)
