import asyncio
from typing import Any

from fastmcp import FastMCP
from fastmcp.server.middleware import CallNext, Middleware, MiddlewareContext
from mcp.server.session import ServerSession


class ToolListChangedClientNotifier(Middleware):
    def __init__(self) -> None:
        self._sessions: set[ServerSession] = set()

    async def on_initialize(
        self,
        context: MiddlewareContext[Any],
        call_next: CallNext[Any, Any],
    ) -> Any:
        result = await call_next(context)
        fastmcp_context = context.fastmcp_context
        if fastmcp_context is not None:
            try:
                self._sessions.add(fastmcp_context.session)
            except RuntimeError:
                pass
        return result

    def notify_tool_list_changed(self) -> bool:
        return self._schedule("send_tool_list_changed")

    def notify_prompt_list_changed(self) -> bool:
        return self._schedule("send_prompt_list_changed")

    def notify_resource_list_changed(self) -> bool:
        return self._schedule("send_resource_list_changed")

    def _schedule(self, method_name: str) -> bool:
        if not self._sessions:
            return False
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return False
        for session in tuple(self._sessions):
            loop.create_task(self._notify_session(session, method_name))
        return True

    async def _notify_session(self, session: ServerSession, method_name: str) -> None:
        try:
            await getattr(session, method_name)()
        except Exception:
            self._sessions.discard(session)


def install_tool_list_changed_notifier(mcp: FastMCP) -> ToolListChangedClientNotifier:
    notifier = ToolListChangedClientNotifier()
    mcp.add_middleware(notifier)
    return notifier
