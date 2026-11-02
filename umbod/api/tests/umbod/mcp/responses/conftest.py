from collections.abc import Iterator

import pytest
from fastmcp.tools import FunctionTool, ToolResult

from tests.support.signals import InMemorySignalFailureHandler
from umbod.core.responses import ToolResponseMetadataFactory
from umbod.mcp.responses.adapter import BuiltinToolResponseAdapter
from umbod.mcp.signals import (
    McpInvocationActor,
    McpInvocationContext,
    McpInvocationCorrelation,
    McpInvocationPublisher,
    McpSignals,
    McpToolInvocationCompleted,
    reset_mcp_invocation_context,
    set_mcp_invocation_context,
)


@pytest.fixture
def adapter() -> BuiltinToolResponseAdapter:
    async def invoke(value: int) -> ToolResult:
        return ToolResult(structured_content={"value": value})

    delegate = FunctionTool.from_function(invoke)
    return BuiltinToolResponseAdapter(
        ToolResponseMetadataFactory("release", "revision"), delegate
    )


@pytest.fixture
def completion_events() -> list[McpToolInvocationCompleted]:
    return []


@pytest.fixture
def publisher(
    completion_events: list[McpToolInvocationCompleted],
) -> Iterator[McpInvocationPublisher]:
    signals = McpSignals(InMemorySignalFailureHandler())
    signals.invocation_completed.connect("test.responses", completion_events.append)
    token = set_mcp_invocation_context(
        McpInvocationContext(
            actor=McpInvocationActor(
                authenticated_user_id="user", agent_client_id="agent"
            ),
            correlation=McpInvocationCorrelation(trace_id="trace", span_id="span"),
            server_name="responses-test",
        )
    )
    try:
        yield McpInvocationPublisher(signals)
    finally:
        reset_mcp_invocation_context(token)
