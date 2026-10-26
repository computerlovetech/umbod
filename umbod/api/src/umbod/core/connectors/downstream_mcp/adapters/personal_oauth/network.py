import base64
from urllib.parse import quote_plus

import anyio
import httpcore

from ...personal_connections.oauth_models import PersonalOAuthProviderFailure
from .transport import BasicOAuthHttpAuthentication, OAuthDestination, OAuthHttpRequest, OAuthHttpResponse
from .validation import MAX_BODY_BYTES, validated_url
from umbod.core.network import resolve_public_addresses


class SafeOAuthHttpTransport:
    def __init__(self, pool: httpcore.AsyncConnectionPool) -> None:
        self._pool = pool

    async def validate_destination(self, command: OAuthDestination) -> None:
        try:
            parts = validated_url(command.url)
            with anyio.fail_after(10):
                await resolve_public_addresses(host=parts.hostname, port=parts.port or 443)
        except Exception:
            raise PersonalOAuthProviderFailure("Personal OAuth provider request failed") from None

    async def request(self, command: OAuthHttpRequest) -> OAuthHttpResponse:
        try:
            validated_url(command.url)
            body = command.body.get_secret_value().encode("utf-8")
            if len(body) > MAX_BODY_BYTES:
                raise ValueError("Request too large")
            headers = [(b"accept", b"application/json")]
            if command.content_type:
                headers.append((b"content-type", command.content_type.encode("ascii")))
            if isinstance(command.authentication, BasicOAuthHttpAuthentication):
                client_id = quote_plus(command.authentication.client_id.get_secret_value(), encoding="utf-8")
                client_secret = quote_plus(command.authentication.client_secret.get_secret_value(), encoding="utf-8")
                credentials = base64.b64encode(f"{client_id}:{client_secret}".encode("ascii"))
                headers.append((b"authorization", b"Basic " + credentials))
            with anyio.fail_after(20):
                async with self._pool.stream(
                    method=command.method, url=command.url, content=body, headers=headers,
                    extensions={"timeout": {"connect": 10.0, "read": 10.0, "write": 10.0, "pool": 10.0}},
                ) as response:
                    if 300 <= response.status < 400:
                        raise ValueError("Redirect is unsupported")
                    for key, value in response.headers:
                        if key.lower() == b"content-encoding" and value.lower() != b"identity":
                            raise ValueError("Encoded responses are unsupported")
                        if key.lower() == b"content-length" and int(value) > MAX_BODY_BYTES:
                            raise ValueError("Response too large")
                    content = bytearray()
                    async for chunk in response.aiter_stream():
                        if len(content) + len(chunk) > MAX_BODY_BYTES:
                            raise ValueError("Response too large")
                        content.extend(chunk)
                    return OAuthHttpResponse(status=response.status, body=bytes(content))
        except Exception:
            raise PersonalOAuthProviderFailure("Personal OAuth provider request failed") from None
