import asyncio
from collections.abc import AsyncIterator
from typing import Any
from uuid import UUID

import httpx
import pytest
from fastapi import APIRouter
from starlette.requests import Request
from starlette.responses import JSONResponse, StreamingResponse
from starlette.routing import Mount, Route
from starlette.types import Message, Receive, Scope, Send

from umbod.build_identity import UMBOD_RELEASE, UMBOD_REVISION
from umbod.http_metadata import (
    HttpMetadataMiddleware,
    HttpMetadataStarlette,
    current_request_id,
    request_id_context,
)
from umbod.rest.factories import RootApiAppFactory, SubApiAppFactory
from umbod.rest.settings import APISettings


def test_source_build_identity_is_explicit() -> None:
    assert UMBOD_RELEASE == "development"
    assert UMBOD_REVISION == "unknown"


def test_nested_request_context_restores_previous_value() -> None:
    assert current_request_id() is None
    with request_id_context("outer"):
        with pytest.raises(RuntimeError), request_id_context("inner"):
            assert current_request_id() == "inner"
            raise RuntimeError("failure")
        assert current_request_id() == "outer"
    assert current_request_id() is None


@pytest.mark.asyncio
@pytest.mark.parametrize("path,status", [("/ok", 200), ("/missing", 404), ("/fail", 500)])
async def test_rest_metadata_covers_success_and_errors(path: str, status: int) -> None:
    app = RootApiAppFactory(APISettings(_env_file=None)).create()

    @app.get("/ok")
    async def ok() -> dict[str, Any]:
        return {"request_id": current_request_id()}

    @app.get("/fail")
    async def fail() -> None:
        raise RuntimeError("failure")

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app, raise_app_exceptions=False), base_url="http://localhost") as client:
        response = await client.get(path, headers={"X-Request-ID": "untrusted"})
    assert response.status_code == status
    assert response.headers["X-Umbod-Version"] == UMBOD_RELEASE
    assert response.headers["X-Umbod-Revision"] == UMBOD_REVISION
    request_id = response.headers["X-Request-ID"]
    assert UUID(hex=request_id).hex == request_id
    assert request_id != "untrusted"
    if status == 200:
        assert response.json()["request_id"] == request_id
    assert current_request_id() is None


@pytest.mark.asyncio
async def test_rest_exposes_metadata_to_cors_clients_and_openapi() -> None:
    settings = APISettings(cors={"origins": ["https://client.example"]}, _env_file=None)
    app = RootApiAppFactory(settings).create()
    app.mount("/api", SubApiAppFactory("test", APIRouter()).create())
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://localhost") as client:
        response = await client.get("/api/openapi.json", headers={"Origin": "https://client.example"})
    assert response.json()["info"]["version"] == UMBOD_RELEASE
    assert response.headers["access-control-allow-origin"] == "https://client.example"
    exposed = response.headers["access-control-expose-headers"].lower()
    assert all(header in exposed for header in ("x-umbod-version", "x-umbod-revision", "x-request-id"))


@pytest.mark.asyncio
async def test_concurrent_and_nested_http_requests_keep_correlation_isolated() -> None:
    async def endpoint(request: Request) -> JSONResponse:
        before = current_request_id()
        await asyncio.sleep(0)
        assert current_request_id() == before
        return JSONResponse({"request_id": before})

    inner = HttpMetadataStarlette(routes=[Route("/ok", endpoint)])
    outer = HttpMetadataStarlette(routes=[Mount("/inner", inner)])
    with request_id_context("parent"):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(outer), base_url="http://localhost") as client:
            responses = await asyncio.gather(*(client.get("/inner/ok") for _ in range(8)))
        assert current_request_id() == "parent"
    ids = {response.headers["X-Request-ID"] for response in responses}
    assert len(ids) == 8
    assert "parent" not in ids
    assert all(response.json()["request_id"] == response.headers["X-Request-ID"] for response in responses)


@pytest.mark.asyncio
async def test_streaming_sends_chunks_before_producer_finishes() -> None:
    first_chunk_sent = asyncio.Event()
    messages: list[Message] = []
    observed_ids: list[str | None] = []

    async def chunks() -> AsyncIterator[bytes]:
        observed_ids.append(current_request_id())
        yield b"first"
        await first_chunk_sent.wait()
        observed_ids.append(current_request_id())
        yield b"second"

    async def endpoint(scope: Scope, receive: Receive, send: Send) -> None:
        await StreamingResponse(chunks())(scope, receive, send)

    async def receive() -> Message:
        return {"type": "http.request", "body": b""}

    async def send(message: Message) -> None:
        messages.append(message)
        if message["type"] == "http.response.body" and message.get("body") == b"first":
            first_chunk_sent.set()

    scope: Scope = {"type": "http", "method": "GET", "path": "/", "headers": [], "asgi": {"spec_version": "2.4"}}
    await asyncio.wait_for(HttpMetadataMiddleware(endpoint)(scope, receive, send), timeout=2)
    headers = dict(messages[0]["headers"])
    assert observed_ids == [headers[b"x-request-id"].decode()] * 2
    assert [message.get("body") for message in messages[1:]] == [b"first", b"second", b""]
    assert current_request_id() is None
