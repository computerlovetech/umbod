import re
from urllib.parse import quote

from umbod.core.filesystem import StorageFailure
from umbod.core.filesystem.content.delivery import ExternalDownloadInstructions, ExternalDownloadRequest

from ..config import S3ContentConfig
from ..keys import validate_key
from .edge import ClientProvider
from .lifecycle import client_scope


async def prepare_download(
    config: S3ContentConfig, provider: ClientProvider, request: ExternalDownloadRequest,
) -> ExternalDownloadInstructions:
    try:
        validate_key(request.content.key)
        key = f"{config.prefix}/{request.content.key}" if config.prefix else request.content.key
        content_type = request.metadata.content_type
        media_type = (
            content_type if isinstance(content_type, str)
            and re.fullmatch(r"[A-Za-z0-9!#$&^_.+-]+/[A-Za-z0-9!#$&^_.+-]+", content_type)
            else "application/octet-stream"
        )
        disposition = "attachment; filename=\"download\"; filename*=UTF-8''" + quote(request.name, safe="")
        async with client_scope(provider) as client:
            url = await client.generate_presigned_url(
                "get_object", Params={
                    "Bucket": config.bucket, "Key": key,
                    "ResponseContentType": media_type,
                    "ResponseContentDisposition": disposition,
                    "ResponseCacheControl": "no-store",
                }, ExpiresIn=300, HttpMethod="GET",
            )
        return ExternalDownloadInstructions(url=url)
    except Exception:
        raise StorageFailure("Cannot prepare download transfer") from None
