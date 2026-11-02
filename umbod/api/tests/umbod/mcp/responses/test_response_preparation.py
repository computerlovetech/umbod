from typing import Any

import pytest
from fastmcp import FastMCP
from fastmcp.tools import ToolResult
from mcp.types import CallToolResult, TextContent

from umbod.mcp.responses.adapter import RESPONSE_METADATA_KEY
from umbod.mcp.signals import McpInvocationPublisher, McpToolInvocationCompleted, McpToolInvocationFailed
from umbod.mcp.tools import McpObservedToolRegistrar


@pytest.mark.asyncio
@pytest.mark.parametrize("boundary", ["serialized_payload_content", "render_response_guidance", "wire_conversion"])
async def test_response_preparation_failure_publishes_one_failure_without_repeating_mutation(
    publisher: McpInvocationPublisher, completion_events: list[McpToolInvocationCompleted],
    monkeypatch: pytest.MonkeyPatch, boundary: str,
) -> None:
    mutations: list[str] = []

    class FailingWireResult(ToolResult):
        def to_mcp_result(self) -> CallToolResult:
            raise ValueError("SECRET wire payload")

    def fail_projection(*arguments: object, **options: object) -> list[TextContent]:
        raise ValueError("SECRET renderer payload")

    async def mutate() -> ToolResult:
        mutations.append("created")
        result_type = FailingWireResult if boundary == "wire_conversion" else ToolResult
        return result_type(structured_content={"value": 4})

    tool = McpObservedToolRegistrar(FastMCP(), publisher).register(
        mutate, name="create_filesystem_file", description="Create.", auth=None, builtin_response=True,
    )
    if boundary != "wire_conversion":
        monkeypatch.setattr(f"umbod.mcp.responses.adapter.{boundary}", fail_projection)

    result = await tool.run({})
    guidance = result.meta[RESPONSE_METADATA_KEY]["guidance"]
    visible = "\n".join(block.text for block in result.content if isinstance(block, TextContent))

    assert mutations == ["created"]
    assert result.is_error
    assert result.structured_content is None
    assert guidance["operation_state"] == "completed"
    assert guidance["recovery"]["retry"] == "inspect_before_retry"
    assert guidance["error"]["code"] == "tool_response_contract_invalid"
    assert "Do not retry automatically" in visible
    assert "original parent" in visible
    assert "SECRET" not in repr(result)
    assert len(completion_events) == 1
    assert isinstance(completion_events[0], McpToolInvocationFailed)
    assert completion_events[0].diagnostic.stage == "output"
    assert completion_events[0].diagnostic.reason == "invalid_output"


@pytest.mark.asyncio
async def test_truncated_argument_issues_publish_a_typed_model_visible_notice(
    publisher: McpInvocationPublisher,
) -> None:
    calls: list[str] = []

    async def invoke(
        first: int, second: int, third: int, fourth: int, fifth: int,
        sixth: int, seventh: int, eighth: int, ninth: int,
    ) -> dict[str, Any]:
        calls.append("executed")
        return {"items": [first, second, third, fourth, fifth, sixth, seventh, eighth, ninth]}

    tool = McpObservedToolRegistrar(FastMCP(), publisher).register(
        invoke, name="builtin", description="Validate.", auth=None, builtin_response=True,
    )
    result = await tool.run({
        name: "SECRET invalid value"
        for name in ("first", "second", "third", "fourth", "fifth", "sixth", "seventh", "eighth", "ninth")
    })
    guidance = result.meta[RESPONSE_METADATA_KEY]["guidance"]
    visible = "\n".join(block.text for block in result.content if isinstance(block, TextContent))

    assert calls == []
    assert result.is_error
    assert guidance["operation_state"] == "not_started"
    assert len(guidance["error"]["issues"]) == 8
    assert guidance["notices"] == [{
        "code": "argument_issues_truncated",
        "message": "Additional issues omitted; correct these fields and retry.",
    }]
    assert guidance["notices"][0]["code"] in visible
    assert guidance["notices"][0]["message"] in visible
    assert "SECRET" not in repr(result)
