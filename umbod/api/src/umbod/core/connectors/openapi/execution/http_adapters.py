from typing import Protocol
from pydantic import ConfigDict, PositiveFloat, PositiveInt

from umbod.core.network.http import (
    AsyncHttpClient,
    HttpRedirectPolicy,
    HttpRequest,
    HttpTimeoutError,
    HttpTlsError,
    HttpTransportError,
    JsonHttpBody,
    NoHttpBody,
)
from umbod.proxies import Model
from umbod.core.invocation.failure_evidence import (
    InvocationFailureOrigin,
    capture_invocation_exception,
)

from umbod.core.connectors.openapi.execution.service import (
    AuthenticatedOutboundRequest,
    ExactHttpsDestinationPolicy,
    OpenApiExecutionResponse,
    OutboundRequest,
    OutboundTransportError,
    TrustedBearerAuthorization,
)


class OutboundPolicyError(OutboundTransportError):
    code = "destination_denied"


class OutboundRedirectError(OutboundTransportError):
    code = "redirect_denied"


class OutboundTimeoutError(OutboundTransportError):
    code = "outbound_timeout"


class OutboundNetworkError(OutboundTransportError):
    code = "outbound_unavailable"


class OutboundTlsError(OutboundTransportError):
    code = "outbound_tls_failed"


class StreamingOutboundOperationAdapter:
    _safe_response_headers = frozenset(
        {"cache-control", "content-language", "etag", "expires", "last-modified", "retry-after"}
    )

    _forbidden_request_headers = frozenset(
        {
            "authorization",
            "cookie",
            "proxy-authorization",
            "host",
            "connection",
            "keep-alive",
            "proxy-authenticate",
            "te",
            "trailer",
            "transfer-encoding",
            "upgrade",
            "forwarded",
            "x-forwarded-for",
            "x-forwarded-host",
            "x-forwarded-proto",
        }
    )

    def __init__(self, client: AsyncHttpClient) -> None:
        self._client = client
        self._policy = ExactHttpsDestinationPolicy()

    async def send(
        self, request: AuthenticatedOutboundRequest | OutboundRequest
    ) -> OpenApiExecutionResponse:
        try:
            destination = self._policy.validate(request.url, request.approved_hosts)
        except ValueError:
            raise OutboundPolicyError() from None
        safe_request_headers = {
            name: value
            for name, value in request.headers.items()
            if name.lower() not in self._forbidden_request_headers
        }
        if isinstance(request, AuthenticatedOutboundRequest) and isinstance(
            request.authorization, TrustedBearerAuthorization
        ):
            safe_request_headers["Authorization"] = (
                f"Bearer {request.authorization.token.get_secret_value()}"
            )
        outgoing = HttpRequest(
            method=request.method,
            url=destination,
            headers=safe_request_headers,
            query={},
            body=JsonHttpBody(request.json_body) if request.has_json_body else NoHttpBody(),
            timeout=request.timeout_seconds,
            redirects=HttpRedirectPolicy.DENY,
        )
        try:
            async with self._client.stream(outgoing) as response:
                if 300 <= response.status_code < 400:
                    raise OutboundRedirectError()
                body = bytearray()
                truncated = False
                async for chunk in response.aiter_bytes():
                    remaining = request.maximum_response_bytes - len(body)
                    if len(chunk) > remaining:
                        body.extend(chunk[:remaining])
                        truncated = True
                        break
                    body.extend(chunk)
                headers = {name.lower(): value for name, value in response.headers.items()}
                content_type = headers.get("content-type", "").split(";", 1)[0].strip().lower()
                safe_headers = {
                    name: value for name, value in headers.items() if name in self._safe_response_headers
                }
                return OpenApiExecutionResponse(
                    status=response.status_code,
                    content_type=content_type,
                    headers=safe_headers,
                    body=bytes(body),
                    truncated=truncated,
                )
        except HttpTransportError as error:
            capture_invocation_exception(error.__cause__ or error, InvocationFailureOrigin.OPENAPI)
            if isinstance(error, HttpTimeoutError):
                raise OutboundTimeoutError() from None
            if isinstance(error, HttpTlsError):
                raise OutboundTlsError() from None
            raise OutboundNetworkError() from None


class SpecificationFetchRequest(Model):
    model_config = ConfigDict(extra="forbid", frozen=True)

    url: str
    approved_hosts: tuple[str, ...]
    timeout_seconds: PositiveFloat = 10.0
    maximum_response_bytes: PositiveInt = 2_000_000


class SpecificationFetcher(Protocol):
    async def fetch(self, request: SpecificationFetchRequest) -> bytes: ...


class StreamingSpecificationFetcher:
    def __init__(
        self, client: AsyncHttpClient, policy: ExactHttpsDestinationPolicy
    ) -> None:
        self._client = client
        self._policy = policy

    async def fetch(self, request: SpecificationFetchRequest) -> bytes:
        url = self._policy.validate(request.url, request.approved_hosts)
        outgoing = HttpRequest(
            method="GET",
            url=url,
            headers={},
            query={},
            body=NoHttpBody(),
            timeout=request.timeout_seconds,
            redirects=HttpRedirectPolicy.DENY,
        )
        async with self._client.stream(outgoing) as response:
            if response.status_code < 200 or response.status_code >= 300:
                raise ValueError("Specification fetch failed")
            body = bytearray()
            async for chunk in response.aiter_bytes():
                if len(body) + len(chunk) > request.maximum_response_bytes:
                    raise ValueError("Specification exceeds response byte limit")
                body.extend(chunk)
            return bytes(body)
