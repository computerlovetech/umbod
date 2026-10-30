from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastmcp import FastMCP
from fastmcp.server.auth.middleware import RequireAuthMiddleware
from fastmcp.server.http import StarletteWithLifespan, StreamableHTTPASGIApp
from mcp.server.streamable_http_manager import RequestBodyLimitMiddleware, StreamableHTTPSessionManager
from starlette.applications import Starlette
from starlette.routing import Route

MAX_MCP_REQUEST_BODY_BYTES = 64 * 1024 * 1024


def configure_request_body_limit(app: Starlette, path: str, max_request_body_bytes: int) -> None:
    endpoints = [route.endpoint for route in app.routes if isinstance(route, Route) and route.path == path]
    if len(endpoints) != 1:
        raise RuntimeError("Unsupported MCP HTTP route composition")
    endpoint = endpoints[0]
    if isinstance(endpoint, RequireAuthMiddleware):
        endpoint = endpoint.app
    if not isinstance(endpoint, StreamableHTTPASGIApp):
        raise RuntimeError("Unsupported MCP HTTP endpoint")
    manager = endpoint.session_manager
    if not isinstance(manager, StreamableHTTPSessionManager):
        raise RuntimeError("MCP HTTP session manager unavailable")
    limiter = manager.asgi_app
    if not isinstance(limiter, RequestBodyLimitMiddleware):
        raise RuntimeError("Unsupported MCP HTTP request body limiter")
    limiter.max_body_size = max_request_body_bytes
    manager.max_request_body_size = max_request_body_bytes


def create_mcp_http_app(
    mcp: FastMCP, *, path: str, stateless_http: bool, max_request_body_bytes: int,
) -> StarletteWithLifespan:
    if max_request_body_bytes <= 0:
        raise ValueError("MCP HTTP request body limit must be positive")
    app = mcp.http_app(path=path, stateless_http=stateless_http)
    original_lifespan = app.router.lifespan_context

    @asynccontextmanager
    async def lifespan(application: Starlette) -> AsyncIterator[None]:
        async with original_lifespan(application):
            configure_request_body_limit(app, path, max_request_body_bytes)
            yield

    app.router.lifespan_context = lifespan
    return app
