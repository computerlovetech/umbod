from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from contextvars import ContextVar
from typing import Optional

from fastmcp.server.auth import AuthContext
from fastmcp.server.middleware import CallNext, Middleware, MiddlewareContext
from fastmcp.tools.base import Tool
from mcp.types import ListToolsRequest

from umbod.core.filesystem.authorization import ResolvedIdentity, VerifiedIdentityResolver
from umbod.core.filesystem.authorization.discovery import FilesystemOperation, permitted_operations
from umbod.mcp.connectors.downstream_mcp.provider import _REQUEST_CONNECTOR_SCOPE

from .ports import FilesystemCallerCapture
from .runtime import FilesystemDiscoveryRuntime


FILESYSTEM_TOOL_OPERATIONS: dict[str, FilesystemOperation] = {
    "filesystem_browse": FilesystemOperation.INSPECT,
    "get_filesystem_root": FilesystemOperation.INSPECT_ROOT,
    "get_filesystem_node": FilesystemOperation.INSPECT,
    "list_filesystem_children": FilesystemOperation.LIST,
    "create_filesystem_file": FilesystemOperation.CREATE,
    "create_filesystem_directory": FilesystemOperation.CREATE,
    "filesystem_upload": FilesystemOperation.CREATE,
    "filesystem_read_file": FilesystemOperation.READ,
    "filesystem_delete_file": FilesystemOperation.DELETE,
    "filesystem_search_sharing_recipients": FilesystemOperation.SHARE,
    "filesystem_share": FilesystemOperation.SHARE,
}


class FilesystemToolVisibility:
    def __init__(
        self, callers: FilesystemCallerCapture, runtime: FilesystemDiscoveryRuntime,
    ) -> None:
        self._callers = callers
        self._runtime = runtime
        self._operations: ContextVar[Optional[frozenset[FilesystemOperation]]] = ContextVar(
            "filesystem_visible_operations", default=None,
        )

    async def capture(self) -> frozenset[FilesystemOperation]:
        if _REQUEST_CONNECTOR_SCOPE.get():
            return frozenset()
        caller = self._callers.capture()
        snapshot = self._runtime.capture()
        identity = await VerifiedIdentityResolver().resolve(caller)
        if not isinstance(identity, ResolvedIdentity):
            return frozenset()
        return permitted_operations(snapshot, identity)

    @asynccontextmanager
    async def discovery_operation(self) -> AsyncIterator[frozenset[FilesystemOperation]]:
        operations = await self.capture()
        token = self._operations.set(operations)
        try:
            yield operations
        finally:
            self._operations.reset(token)

    async def authorize(self, context: AuthContext) -> bool:
        operations = self._operations.get()
        if operations is None:
            operations = await self.capture()
        return self.allows(context.component.name, operations)

    def allows(self, name: str, operations: frozenset[FilesystemOperation]) -> bool:
        return not _REQUEST_CONNECTOR_SCOPE.get() and FILESYSTEM_TOOL_OPERATIONS[name] in operations


class FilesystemVisibilityMiddleware(Middleware):
    def __init__(self, visibility: FilesystemToolVisibility) -> None:
        self._visibility = visibility

    async def on_list_tools(
        self,
        context: MiddlewareContext[ListToolsRequest],
        call_next: CallNext[ListToolsRequest, Sequence[Tool]],
    ) -> Sequence[Tool]:
        async with self._visibility.discovery_operation() as operations:
            tools = await call_next(context)
            return [
                tool for tool in tools
                if tool.name not in FILESYSTEM_TOOL_OPERATIONS
                or self._visibility.allows(tool.name, operations)
            ]
