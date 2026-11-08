import hashlib
from datetime import datetime, timezone
from urllib.parse import parse_qs, urlsplit

from pydantic import BaseModel, ConfigDict

from umbod.core.filesystem import ContentRef, StorageFailure
from umbod.core.filesystem.uploads.errors import UploadConflict, UploadLengthMismatch, UploadMediaTypeMismatch
from umbod.core.filesystem.uploads.models import (
    ExternalTransferInstructions, ExternalTransferRequest, UploadedContent, VerifiedReceipt,
)

from ..config import S3ContentConfig
from .edge import ClientProvider, ResponseBody
from .lifecycle import client_scope, finish, settle


class TransferMetadata(BaseModel):
    model_config = ConfigDict(strict=True)

    ContentLength: int
    ContentType: str


class S3UploadTransfer:
    def __init__(self, config: S3ContentConfig, provider: ClientProvider) -> None:
        self._config = config
        self._provider = provider

    @property
    def max_transfer_bytes(self) -> int:
        return 5 * 1024 ** 3

    def _key(self, request: ExternalTransferRequest) -> str:
        key = request.transfer.storage_key
        return f"{self._config.prefix}/{key}" if self._config.prefix else key

    async def prepare_transfer(self, request: ExternalTransferRequest) -> ExternalTransferInstructions:
        if request.size_bytes > self.max_transfer_bytes:
            raise StorageFailure("Upload exceeds storage transfer limit")
        seconds = min(900, int((request.transfer.expires_at - datetime.now(timezone.utc)).total_seconds()))
        if seconds <= 0:
            raise StorageFailure("Upload transfer expired")
        try:
            async with client_scope(self._provider) as client:
                url = await client.generate_presigned_url(
                    "put_object", Params={
                        "Bucket": self._config.bucket, "Key": self._key(request),
                        "ContentLength": request.size_bytes, "ContentType": request.content_type,
                        "IfNoneMatch": "*",
                    }, ExpiresIn=seconds, HttpMethod="PUT",
                )
            signed = parse_qs(urlsplit(url).query).get("X-Amz-SignedHeaders", [""])[0].split(";")
            if not {"host", "content-length", "content-type", "if-none-match"}.issubset(signed):
                raise StorageFailure("Storage does not support conditional upload signing")
            return ExternalTransferInstructions(
                url=url, headers={"Content-Type": request.content_type, "If-None-Match": "*"},
            )
        except Exception:
            raise StorageFailure("Cannot prepare upload transfer") from None

    async def verify_transfer(self, request: ExternalTransferRequest) -> UploadedContent:
        from botocore.exceptions import ClientError

        responses: list[object] = []
        try:
            async with client_scope(self._provider) as client:
                try:
                    response = await settle(client.get_object(
                        Bucket=self._config.bucket, Key=self._key(request),
                    ), responses.append)
                    if not isinstance(response, dict) or not isinstance(response.get("Body"), ResponseBody):
                        raise StorageFailure("Invalid upload response")
                    metadata = TransferMetadata.model_validate(response)
                    if metadata.ContentLength != request.size_bytes:
                        raise UploadLengthMismatch()
                    if metadata.ContentType != request.content_type:
                        raise UploadMediaTypeMismatch()
                    body = response["Body"]
                    digest = hashlib.sha256()
                    size = 0
                    while True:
                        chunk = await finish(body.read(min(65536, request.size_bytes - size + 1)))
                        if not isinstance(chunk, bytes) or len(chunk) > 65536:
                            raise StorageFailure("Invalid upload response")
                        size += len(chunk)
                        if size > request.size_bytes:
                            raise UploadLengthMismatch()
                        if not chunk:
                            break
                        digest.update(chunk)
                    if size != request.size_bytes:
                        raise UploadLengthMismatch()
                    return UploadedContent(
                        content=ContentRef(key=request.transfer.storage_key, size=size),
                        receipt=VerifiedReceipt(size_bytes=size, sha256=digest.hexdigest()),
                    )
                finally:
                    for response in responses:
                        if isinstance(response, dict) and isinstance(response.get("Body"), ResponseBody):
                            response["Body"].close()
        except (UploadLengthMismatch, UploadMediaTypeMismatch):
            raise
        except ClientError as error:
            if error.response.get("Error", {}).get("Code") in ("NoSuchKey", "404", "NotFound"):
                raise UploadConflict() from None
            raise StorageFailure("Cannot verify upload content") from None
        except Exception:
            raise StorageFailure("Cannot verify upload content") from None
