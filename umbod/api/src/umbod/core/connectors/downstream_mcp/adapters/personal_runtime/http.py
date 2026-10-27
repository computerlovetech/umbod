from collections.abc import AsyncIterator, Iterator
from contextlib import contextmanager
from typing import Protocol

import anyio
import httpcore2
import httpx2

from umbod.core.invocation.diagnostics import InvocationFailureDiagnostic
from umbod.core.invocation.failure_evidence import (
    InvocationFailureOrigin,
    capture_invocation_exception,
    current_invocation_failure,
)

from umbod.core.connectors.downstream_mcp.personal_connections.runtime_models import PersonalRuntimeUnavailable

from .operation import OperationState
from .wire_parsing import ProtocolInputValidator, ValidatedProtocolStream


_TIMEOUT = InvocationFailureDiagnostic(execution_mode="personal", stage="transport", reason="timeout")


class ResponseBody(Protocol):
    def aiter_stream(self) -> AsyncIterator[bytes]: ...

    async def aclose(self) -> None: ...


_CORE_ERRORS = (
    (httpcore2.ConnectTimeout, httpx2.ConnectTimeout),
    (httpcore2.ReadTimeout, httpx2.ReadTimeout),
    (httpcore2.WriteTimeout, httpx2.WriteTimeout),
    (httpcore2.PoolTimeout, httpx2.PoolTimeout),
    (httpcore2.ConnectError, httpx2.ConnectError),
    (httpcore2.ReadError, httpx2.ReadError),
    (httpcore2.WriteError, httpx2.WriteError),
    (httpcore2.ProxyError, httpx2.ProxyError),
    (httpcore2.RemoteProtocolError, httpx2.RemoteProtocolError),
    (httpcore2.LocalProtocolError, httpx2.LocalProtocolError),
    (httpcore2.UnsupportedProtocol, httpx2.UnsupportedProtocol),
    (httpcore2.TimeoutException, httpx2.TimeoutException),
    (httpcore2.NetworkError, httpx2.NetworkError),
    (httpcore2.ProtocolError, httpx2.ProtocolError),
)


@contextmanager
def safe_core_errors() -> Iterator[None]:
    try:
        yield
    except Exception as error:
        for core_error, http_error in _CORE_ERRORS:
            if isinstance(error, core_error):
                if current_invocation_failure() is None:
                    capture_invocation_exception(error, InvocationFailureOrigin.MCP)
                raise http_error("Personal MCP unavailable") from None
        raise


def _capture_http_failure(error: Exception) -> None:
    if current_invocation_failure() is None:
        origin = InvocationFailureOrigin.MCP if isinstance(error, (TimeoutError, httpx2.HTTPError, PersonalRuntimeUnavailable)) else InvocationFailureOrigin.INTERNAL
        capture_invocation_exception(error, origin)


class BoundedResponseStream(httpx2.AsyncByteStream):
    def __init__(self, body: ResponseBody, state: OperationState) -> None:
        self._body = body
        self._state = state
        self._size = 0

    async def __aiter__(self) -> AsyncIterator[bytes]:
        iterator = self._body.aiter_stream()
        while True:
            try:
                with anyio.fail_after(max(0, self._state.deadline - anyio.current_time())), safe_core_errors():
                    chunk = await anext(iterator)
            except StopAsyncIteration:
                return
            except (TimeoutError, httpx2.TimeoutException) as error:
                _capture_http_failure(error)
                self._state.fail(_TIMEOUT)
            except Exception as error:
                _capture_http_failure(error)
                self._state.fail(None)
            self._size += len(chunk)
            self._state.account(len(chunk), self._size)
            yield chunk

    async def aclose(self) -> None:
        with anyio.move_on_after(0.25, shield=True), safe_core_errors():
            await self._body.aclose()


class PersonalHttpTransport(httpx2.AsyncBaseTransport):
    def __init__(self, pool: httpcore2.AsyncConnectionPool, state: OperationState) -> None:
        self._connections = pool
        self._state = state

    async def handle_async_request(self, request: httpx2.Request) -> httpx2.Response:
        body = await self._request_body(request)
        self._state.authorize(request, body)
        response = await self._send(self._outgoing(request, body))
        try:
            return self._response(request, response)
        except Exception as error:
            _capture_http_failure(error)
            with anyio.move_on_after(0.25, shield=True):
                await response.aclose()
        self._state.fail(None)

    async def _request_body(self, request: httpx2.Request) -> bytes:
        body = bytearray()
        async for chunk in request.stream:
            if len(body) + len(chunk) > self._state.limits.maximum_request_bytes:
                self._state.fail(None)
            body.extend(chunk)
        return bytes(body)

    def _outgoing(self, request: httpx2.Request, body: bytes) -> httpcore2.Request:
        allowed_headers = {b"accept", b"content-type", b"content-length", b"host", b"authorization", b"mcp-session-id", b"mcp-protocol-version"}
        headers = [(name, value) for name, value in request.headers.raw if name.lower() in allowed_headers]
        headers.append((b"accept-encoding", b"identity"))
        return httpcore2.Request(
            method=request.method,
            url=httpcore2.URL(
                scheme=request.url.raw_scheme, host=request.url.raw_host,
                port=request.url.port, target=request.url.raw_path,
            ),
            headers=headers,
            content=bytes(body),
            extensions={"timeout": request.extensions.get("timeout", {})},
        )
    async def _send(self, outgoing: httpcore2.Request) -> httpcore2.Response:
        try:
            with anyio.fail_after(max(0, self._state.deadline - anyio.current_time())), safe_core_errors():
                return await self._connections.handle_async_request(outgoing)
        except (TimeoutError, httpx2.TimeoutException) as error:
            _capture_http_failure(error)
            self._state.fail(_TIMEOUT)
        except Exception as error:
            _capture_http_failure(error)
        self._state.fail(None)

    def _response(self, request: httpx2.Request, response: httpcore2.Response) -> httpx2.Response:
        if response.status == 401 and request.method != "DELETE" and not self._state.cleaning_up:
            self._state.authorization_rejected = True
            self._state.fail(None)
        incoming = self._response_headers(response)
        raw = BoundedResponseStream(response, self._state)
        media_type = incoming.get("content-type", "").partition(";")[0].strip().lower()
        return httpx2.Response(
            status_code=response.status,
            headers=incoming,
            stream=ValidatedProtocolStream(raw, self._state, media_type, response.status in {202, 204} or request.method == "DELETE"),
        )

    def _response_headers(self, response: httpcore2.Response) -> httpx2.Headers:
        incoming = httpx2.Headers(response.headers)
        validator = ProtocolInputValidator(self._state)
        allowed = {"content-type", "content-length", "mcp-session-id", "mcp-protocol-version"}
        permitted = httpx2.Headers([(name, value) for name, value in incoming.multi_items() if name in allowed])
        for value in permitted.values():
            validator.text(value)
        self._validate_encoding(permitted)
        encoding = incoming.get("content-encoding", "identity").lower()
        length = int(incoming.get("content-length", "0"))
        if (
            encoding != "identity" or length < 0
            or length > self._state.limits.maximum_response_bytes
            or length + self._state.total_bytes > self._state.limits.maximum_total_bytes
            or response.status < 200 or response.status >= 300
        ):
            self._state.fail(None)
        return permitted

    def _validate_encoding(self, headers: httpx2.Headers) -> None:
        content_type = headers.get("content-type", "")
        parts = content_type.split(";")
        for parameter in parts[1:]:
            name, _, value = parameter.partition("=")
            if name.strip().lower().startswith("charset") and value.strip().strip('"').lower() not in {"utf-8", "utf8"}:
                self._state.fail(None)
        if parts[0].strip().lower() in {"application/json", "text/event-stream"}:
            headers["content-type"] = parts[0].strip().lower() + "; charset=utf-8"

    async def aclose(self) -> None:
        with anyio.move_on_after(0.25, shield=True), safe_core_errors():
            await self._connections.aclose()
