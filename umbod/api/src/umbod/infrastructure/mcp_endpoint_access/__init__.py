from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from umbod.core.connectors.downstream_mcp.endpoint_access import (
    AnonymousMcpInitialization,
)
from umbod.core.network import public_http_connection_pool

from .adapter import PublicMcpInitialization

__all__ = ["open_anonymous_mcp_initialization"]


@asynccontextmanager
async def open_anonymous_mcp_initialization() -> AsyncIterator[
    AnonymousMcpInitialization
]:
    async with public_http_connection_pool(max_connections=1) as pool:
        yield PublicMcpInitialization(
            pool, timeout_seconds=10, maximum_response_bytes=262_144
        )
