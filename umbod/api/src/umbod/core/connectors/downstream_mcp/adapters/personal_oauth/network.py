import base64
from urllib.parse import quote_plus

import anyio
import httpcore

from ...personal.oauth.failures import OAuthFailureEvidence
from umbod.core.invocation.diagnostics import DownstreamHttpResponse, DownstreamResponseEvidence, NoDownstreamResponse
from .failure import OAuthOperationProgress, OAuthTransportFailure, adapter_failure_evidence, rejected_response
from .transport import BasicOAuthHttpAuthentication, OAuthDestination, OAuthHttpRequest, OAuthHttpResponse
from .validation import MAX_BODY_BYTES, validated_url
from umbod.core.network import resolve_public_addresses


def request_cancellation(error: BaseException) -> BaseException | None:
    current: BaseException | None = error
    visited: set[int] = set()
    for _ in range(8):
        if current is None or id(current) in visited:
            break
        visited.add(id(current))
        if isinstance(current, anyio.get_cancelled_exc_class()):
            return current
        current = current.__cause__ or current.__context__
    return None


class SafeOAuthHttpTransport:
    def __init__(self, pool: httpcore.AsyncConnectionPool) -> None:
        self._pool = pool

    async def validate_destination(self, command: OAuthDestination) -> None:
        try:
            parts = validated_url(command.url)
            with anyio.fail_after(10):
                await resolve_public_addresses(host=parts.hostname, port=parts.port or 443)
        except Exception as error:
            raise OAuthTransportFailure(adapter_failure_evidence(error, "discovery")) from None

    async def request(self, command: OAuthHttpRequest) -> OAuthHttpResponse:
        return await self.request_with_progress(command, OAuthOperationProgress("discovery"))

    async def request_with_progress(self, command: OAuthHttpRequest, progress: OAuthOperationProgress) -> OAuthHttpResponse:
        evidence: OAuthFailureEvidence | None = None
        cancellation: BaseException | None = None
        deadline: anyio.CancelScope | None = None
        downstream_response: DownstreamResponseEvidence = NoDownstreamResponse()
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
            with anyio.fail_after(20) as deadline:
                async with self._pool.stream(
                    method=command.method, url=command.url, content=body, headers=headers,
                    extensions={"timeout": {"connect": 10.0, "read": 10.0, "write": 10.0, "pool": 10.0}},
                ) as response:
                    downstream_response = DownstreamHttpResponse(status_code=response.status)
                    progress.evidence = progress.evidence.model_copy(update={"downstream_response": downstream_response})
                    if not 200 <= response.status < 300:
                        evidence = rejected_response(progress.stage, response.status).evidence
                        progress.evidence = evidence
                    try:
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
                    except BaseException as error:
                        cancellation = request_cancellation(error)
                        if cancellation is not None:
                            raise cancellation
                        if isinstance(error, Exception) and evidence is None:
                            evidence = adapter_failure_evidence(error, progress.stage).model_copy(update={
                                "downstream_response": downstream_response,
                                "reason": "invalid_response" if isinstance(error, (ValueError, httpcore.ProtocolError)) else adapter_failure_evidence(error, progress.stage).reason,
                            })
                            progress.evidence = evidence
                        raise
        except Exception as error:
            cancellation = cancellation or request_cancellation(error)
            if cancellation is not None and (deadline is None or not deadline.cancel_called):
                raise cancellation
            if evidence is None and deadline is not None and deadline.cancel_called and (cancellation is not None or isinstance(error, TimeoutError)):
                evidence = progress.evidence
            if evidence is None:
                evidence = adapter_failure_evidence(error, progress.stage).model_copy(update={
                    "downstream_response": downstream_response,
                    "reason": "invalid_response" if isinstance(error, (ValueError, httpcore.ProtocolError)) else adapter_failure_evidence(error, progress.stage).reason,
                })
            progress.evidence = evidence
            raise OAuthTransportFailure(evidence) from None
