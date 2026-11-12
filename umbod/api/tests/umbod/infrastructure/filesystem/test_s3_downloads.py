import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import cast
from urllib.parse import parse_qs, urlsplit

import pytest

from umbod.core.filesystem import ContentRef, NodeMetadata, StorageFailure
from umbod.core.filesystem.content.delivery import ExternalDownloadRequest, ExternalDownloadTransfer
from umbod.core.filesystem.models import UnspecifiedContentType
from umbod.infrastructure.filesystem.s3.edge import S3Client, SDKClientProvider
from umbod.infrastructure.filesystem.s3_content import S3Content
from tests.umbod.infrastructure.filesystem.test_s3_content import FakeBackend, FakeClient, configuration


class DownloadClient(FakeClient):
    async def generate_presigned_url(self, operation: str, **kwargs: object) -> str:
        await self._call(operation, kwargs)
        return cast(DownloadBackend, self.backend).url


class DownloadBackend(FakeBackend):
    def __init__(self) -> None:
        super().__init__()
        self.url = "https://storage.example.test/object?signature=secret"

    @asynccontextmanager
    async def provider(self) -> AsyncIterator[S3Client]:
        self.opens += 1
        self.active += 1
        try:
            await self.step("enter")
            yield cast(S3Client, DownloadClient(self))
        finally:
            await self.step("exit")
            self.active -= 1


def download_request(
    name: str = "report.txt", content_type: str | UnspecifiedContentType = "text/plain",
) -> ExternalDownloadRequest:
    return ExternalDownloadRequest(
        content=ContentRef(key="a" * 32, size=123), name=name,
        metadata=NodeMetadata(content_type=content_type, attributes={}),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("prefix", ["", "private/nested"])
async def test_download_signs_get_with_fixed_overrides_without_reading_objects(prefix: str) -> None:
    backend = DownloadBackend()
    config = configuration().model_copy(update={"prefix": prefix})
    transfer = S3Content(config, backend.provider)
    assert isinstance(transfer, ExternalDownloadTransfer)
    instructions = await transfer.prepare_download(download_request())
    assert backend.calls == [("get_object", {
        "Params": {
            "Bucket": "test-bucket", "Key": f"{prefix}/" + "a" * 32 if prefix else "a" * 32,
            "ResponseContentType": "text/plain",
            "ResponseContentDisposition": "attachment; filename=\"download\"; filename*=UTF-8''report.txt",
            "ResponseCacheControl": "no-store",
        }, "ExpiresIn": 300, "HttpMethod": "GET",
    })]
    assert backend.bodies == []
    assert instructions.url == backend.url
    assert "secret" not in repr(instructions)
    assert backend.active == 0


@pytest.mark.asyncio
async def test_sdk_download_signature_contains_encoded_unicode_attachment_and_five_minute_expiry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing-access-key")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing-secret-key")
    monkeypatch.setenv("AWS_SESSION_TOKEN", "testing-session-token")
    config = configuration().model_copy(update={
        "endpoint_url": "https://storage.example.test", "prefix": "private/nested", "addressing_style": "path",
    })
    instructions = await S3Content(config, SDKClientProvider(config)).prepare_download(
        download_request('résumé "雪"\r\n.txt'),
    )
    parsed = urlsplit(instructions.url)
    query = parse_qs(parsed.query)
    assert parsed.path == "/test-bucket/private/nested/" + "a" * 32
    assert query["X-Amz-Expires"] == ["300"]
    assert query["response-content-type"] == ["text/plain"]
    assert query["response-cache-control"] == ["no-store"]
    assert query["response-content-disposition"] == [
        "attachment; filename=\"download\"; filename*=UTF-8''r%C3%A9sum%C3%A9%20%22%E9%9B%AA%22%0D%0A.txt",
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("content_type", [
    "", "text/plain; charset=utf-8", "text/plain\r\nX-Injected: yes", "text/plain\n", " text/plain",
    "text/*", UnspecifiedContentType(),
])
async def test_invalid_or_unspecified_media_type_uses_safe_fallback(content_type: str | UnspecifiedContentType) -> None:
    backend = DownloadBackend()
    await S3Content(configuration(), backend.provider).prepare_download(download_request(content_type=content_type))
    params = cast(dict[str, object], backend.calls[0][1]["Params"])
    assert params["ResponseContentType"] == "application/octet-stream"


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["enter", "get_object", "exit"])
async def test_signing_and_client_failures_are_sanitized(failure: str) -> None:
    backend = DownloadBackend()
    backend.failure = failure
    with pytest.raises(StorageFailure) as caught:
        await S3Content(configuration(), backend.provider).prepare_download(download_request())
    assert str(caught.value) == "Cannot prepare download transfer"
    assert caught.value.__cause__ is None
    assert caught.value.__suppress_context__


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["enter", "get_object", "exit"])
async def test_cancellation_is_preserved_and_client_is_closed(operation: str) -> None:
    backend = DownloadBackend()
    backend.block = operation
    task = asyncio.create_task(S3Content(configuration(), backend.provider).prepare_download(download_request()))
    await asyncio.wait_for(backend.entered.wait(), 2)
    task.cancel()
    backend.release.set()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(task, 2)
    assert backend.active == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("key", ["", "../secret", "a/b", "A" * 32, "a" * 31, "a" * 32 + "\n"])
async def test_invalid_storage_key_fails_without_client_access(key: str) -> None:
    backend = DownloadBackend()
    request = download_request().model_copy(update={"content": ContentRef(key=key, size=123)})
    with pytest.raises(StorageFailure, match="^Cannot prepare download transfer$"):
        await S3Content(configuration(), backend.provider).prepare_download(request)
    assert backend.opens == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("url", [
    "", "/relative", "ftp://storage.example.test/object", "https://user:password@storage.example.test/object",
    "https://storage.example.test/object#secret", "https://storage.example.test/object\n",
    "https://storage.example.test/object with-space", "https://storage.example.test/object\x00",
])
async def test_unsafe_signed_urls_are_rejected_with_sanitized_failure(url: str) -> None:
    backend = DownloadBackend()
    backend.url = url
    with pytest.raises(StorageFailure) as caught:
        await S3Content(configuration(), backend.provider).prepare_download(download_request())
    assert str(caught.value) == "Cannot prepare download transfer"
    assert caught.value.__cause__ is None
    assert caught.value.__suppress_context__
    assert backend.active == 0
