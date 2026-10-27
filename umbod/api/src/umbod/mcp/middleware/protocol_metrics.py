import asyncio
import logging
from collections.abc import AsyncIterator, Callable, Sequence
from contextlib import asynccontextmanager

import mcp.types as mt
from fastmcp.server.middleware.middleware import CallNext, Middleware, MiddlewareContext
from fastmcp.tools.base import Tool

from umbod.mcp.metrics.protocol_models import (
    CompletedProtocolRequest,
    ProtocolMethod,
    ProtocolOutcome,
    SuccessfulToolsList,
)
from umbod.mcp.metrics.protocol_recorder import McpProtocolMetricsRecorder


logger = logging.getLogger(__name__)


class McpProtocolMetricsMiddleware(Middleware):
    def __init__(
        self,
        recorder: McpProtocolMetricsRecorder,
        clock: Callable[[], float],
    ) -> None:
        self._recorder = recorder
        self._clock = clock

    async def on_initialize(
        self,
        context: MiddlewareContext[mt.InitializeRequest],
        call_next: CallNext[mt.InitializeRequest, mt.InitializeResult | None],
    ) -> mt.InitializeResult | None:
        async with self._request(ProtocolMethod.INITIALIZE):
            return await call_next(context)

    async def on_list_tools(
        self,
        context: MiddlewareContext[mt.ListToolsRequest],
        call_next: CallNext[mt.ListToolsRequest, Sequence[Tool]],
    ) -> Sequence[Tool]:
        async with self._request(ProtocolMethod.LIST_TOOLS):
            result = await call_next(context)
        try:
            self._recorder.record_tools_list(SuccessfulToolsList(tool_count=len(result)))
        except Exception:
            logger.warning("MCP protocol metrics recording failed")
        return result

    @asynccontextmanager
    async def _request(self, method: ProtocolMethod) -> AsyncIterator[None]:
        try:
            started = self._clock()
        except Exception:
            logger.warning("MCP protocol metrics clock failed")
            yield
            return
        outcome = ProtocolOutcome.SUCCESS
        try:
            yield
        except asyncio.CancelledError:
            outcome = ProtocolOutcome.CANCELLED
            raise
        except Exception:
            outcome = ProtocolOutcome.ERROR
            raise
        finally:
            try:
                self._recorder.record_protocol_request(CompletedProtocolRequest(
                    method=method,
                    outcome=outcome,
                    duration_seconds=self._clock() - started,
                ))
            except Exception:
                logger.warning("MCP protocol metrics recording failed")
