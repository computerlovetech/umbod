from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Optional
from uuid import uuid4

from starlette.applications import Starlette
from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from umbod.build_identity import UMBOD_RELEASE, UMBOD_REVISION

_request_id: ContextVar[Optional[str]] = ContextVar("umbod_request_id", default=None)


def current_request_id() -> Optional[str]:
    return _request_id.get()


@contextmanager
def request_id_context(request_id: str) -> Iterator[None]:
    token = _request_id.set(request_id)
    try:
        yield
    finally:
        _request_id.reset(token)


class HttpMetadataMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        existing_request_id = scope.get("umbod.request_id")
        request_id = (
            existing_request_id
            if existing_request_id is not None and existing_request_id == current_request_id()
            else uuid4().hex
        )
        scope["umbod.request_id"] = request_id
        token = _request_id.set(request_id)

        async def send_with_metadata(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers["X-Umbod-Version"] = UMBOD_RELEASE
                headers["X-Umbod-Revision"] = UMBOD_REVISION
                headers["X-Request-ID"] = request_id
            await send(message)

        try:
            await self.app(scope, receive, send_with_metadata)
        finally:
            _request_id.reset(token)
            if existing_request_id is None:
                scope.pop("umbod.request_id", None)
            else:
                scope["umbod.request_id"] = existing_request_id


class HttpMetadataStarlette(Starlette):
    def build_middleware_stack(self) -> ASGIApp:
        return HttpMetadataMiddleware(super().build_middleware_stack())
