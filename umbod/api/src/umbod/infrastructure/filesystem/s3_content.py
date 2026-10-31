import asyncio
from collections.abc import AsyncIterator
from contextlib import aclosing
from uuid import uuid4

from umbod.core.filesystem import ByteStream, ContentRef, StorageFailure, StorageKey

from .config import S3ContentConfig
from .keys import validate_key
from .s3.edge import (
    ClientProvider,
    ObjectMetadata,
    ObjectWritten,
    ResponseBody,
    S3Client,
    UploadCreated,
)
from .s3.lifecycle import client_scope, finish, settle

PART_SIZE = 8 * 1024 * 1024
MAX_PARTS = 10000
READ_SIZE = 64 * 1024


class ContentSourceFailure(Exception):
    def __init__(self, error: Exception) -> None:
        super().__init__()
        self.error: Exception = error


async def source_chunks(data: ByteStream) -> ByteStream:
    try:
        async for chunk in data:
            yield chunk
    except Exception as error:
        raise ContentSourceFailure(error) from None


async def stream_parts(data: ByteStream) -> AsyncIterator[bytes]:
    buffer = bytearray()
    async for chunk in source_chunks(data):
        if not isinstance(chunk, bytes):
            raise StorageFailure("Content stream must yield bytes")
        view = memoryview(chunk)
        for offset in range(0, len(view), PART_SIZE):
            piece = view[offset:offset + PART_SIZE]
            while piece:
                count = min(PART_SIZE - len(buffer), len(piece))
                buffer.extend(piece[:count])
                piece = piece[count:]
                if len(buffer) == PART_SIZE:
                    yield bytes(buffer)
                    buffer.clear()
    if buffer:
        yield bytes(buffer)


class MultipartWrite:
    def __init__(self, client: S3Client, bucket: str, key: str) -> None:
        self._client = client
        self._location = {"Bucket": bucket, "Key": key}
        self._upload_ids: list[str] = []
        self._parts: list[dict[str, object]] = []

    def _created(self, response: object) -> None:
        self._upload_ids.append(UploadCreated.model_validate(response).UploadId)

    async def create(self) -> None:
        await settle(self._client.create_multipart_upload(**self._location), self._created)

    async def upload(self, body: bytes) -> None:
        if len(self._parts) >= MAX_PARTS:
            raise StorageFailure("Content exceeds storage part limit")
        number = len(self._parts) + 1
        response = await finish(self._client.upload_part(
            **self._location, UploadId=self._upload_ids[0], PartNumber=number, Body=body,
        ))
        tag = ObjectWritten.model_validate(response).ETag
        self._parts.append({"ETag": tag, "PartNumber": number})

    async def complete(self) -> None:
        response = await finish(self._client.complete_multipart_upload(
            **self._location, UploadId=self._upload_ids[0],
            MultipartUpload={"Parts": self._parts}, IfNoneMatch="*",
        ))
        ObjectWritten.model_validate(response)

    async def abort(self) -> None:
        if self._upload_ids:
            try:
                await finish(self._client.abort_multipart_upload(
                    **self._location, UploadId=self._upload_ids[0],
                ))
            except (Exception, asyncio.CancelledError):
                pass


class S3Content:
    def __init__(self, config: S3ContentConfig, provider: ClientProvider) -> None:
        self._config = config
        self._provider = provider

    def _object_key(self, key: StorageKey) -> str:
        return f"{self._config.prefix}/{key}" if self._config.prefix else key

    async def put(self, data: ByteStream) -> ContentRef:
        key = uuid4().hex
        try:
            async with client_scope(self._provider) as client:
                return await self._put(client, key, data)
        except ContentSourceFailure as error:
            raise error.error from None
        except Exception:
            raise StorageFailure("Cannot store content object") from None

    async def _put(self, client: S3Client, key: str, data: ByteStream) -> ContentRef:
        parts = stream_parts(data)
        try:
            first = await anext(parts, b"")
            second = await anext(parts, b"")
            if not second:
                response = await finish(client.put_object(
                    Bucket=self._config.bucket, Key=self._object_key(key),
                    Body=first, IfNoneMatch="*",
                ))
                ObjectWritten.model_validate(response)
                return ContentRef(key=key, size=len(first))
            upload = MultipartWrite(client, self._config.bucket, self._object_key(key))
            try:
                await upload.create()
                await upload.upload(first)
                await upload.upload(second)
                size = len(first) + len(second)
                del first, second
                async for part in parts:
                    await upload.upload(part)
                    size += len(part)
                await upload.complete()
                return ContentRef(key=key, size=size)
            except BaseException:
                await upload.abort()
                raise
        finally:
            await parts.aclose()

    async def get(self, key: StorageKey) -> ByteStream:
        validate_key(key)
        try:
            async with client_scope(self._provider) as client:
                async with aclosing(self._read(client, self._object_key(key))) as stream:
                    async for chunk in stream:
                        yield chunk
        except Exception:
            raise StorageFailure("Cannot read content object") from None

    async def _read(self, client: S3Client, key: str) -> ByteStream:
        responses: list[object] = []
        try:
            response = await settle(client.get_object(
                Bucket=self._config.bucket, Key=key,
            ), responses.append)
            if not isinstance(response, dict) or not isinstance(response.get("Body"), ResponseBody):
                raise StorageFailure("Invalid content response")
            body = response["Body"]
            expected = ObjectMetadata.model_validate(response).ContentLength
            size = 0
            while True:
                chunk = await finish(body.read(READ_SIZE))
                if not isinstance(chunk, bytes) or len(chunk) > READ_SIZE:
                    raise StorageFailure("Invalid content response")
                size += len(chunk)
                if size > expected:
                    raise StorageFailure("Invalid content size")
                if not chunk:
                    if size != expected:
                        raise StorageFailure("Invalid content size")
                    break
                yield chunk
        finally:
            for response in responses:
                if isinstance(response, dict):
                    body = response.get("Body")
                    if isinstance(body, ResponseBody):
                        try:
                            body.close()
                        except Exception:
                            pass
