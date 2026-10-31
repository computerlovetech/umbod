from contextlib import AbstractAsyncContextManager
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

from ..config import S3ContentConfig


@runtime_checkable
class ResponseBody(Protocol):
    async def read(self, amount: int) -> bytes: ...
    def close(self) -> None: ...


class S3Client(Protocol):
    async def put_object(self, **kwargs: object) -> object: ...
    async def get_object(self, **kwargs: object) -> object: ...
    async def create_multipart_upload(self, **kwargs: object) -> object: ...
    async def upload_part(self, **kwargs: object) -> object: ...
    async def complete_multipart_upload(self, **kwargs: object) -> object: ...
    async def abort_multipart_upload(self, **kwargs: object) -> object: ...


class ClientProvider(Protocol):
    def __call__(self) -> AbstractAsyncContextManager[S3Client]: ...


class UploadCreated(BaseModel):
    model_config = ConfigDict(strict=True)
    UploadId: str = Field(min_length=1)


class ObjectWritten(BaseModel):
    model_config = ConfigDict(strict=True)
    ETag: str = Field(min_length=1)


class ObjectMetadata(BaseModel):
    model_config = ConfigDict(strict=True)
    ContentLength: int = Field(ge=0)


class SDKClientProvider:
    def __init__(self, config: S3ContentConfig) -> None:
        self._config = config

    def __call__(self) -> AbstractAsyncContextManager[S3Client]:
        from aiobotocore.config import AioConfig
        from aiobotocore.session import get_session

        options: dict[str, object] = {
            "region_name": self._config.region,
            "config": AioConfig(
                signature_version="s3v4",
                connect_timeout=10,
                read_timeout=60,
                retries={"mode": "standard", "total_max_attempts": 3},
                s3={"addressing_style": self._config.addressing_style},
            ),
        }
        if self._config.endpoint_url:
            options["endpoint_url"] = self._config.endpoint_url
        return get_session().create_client("s3", **options)
