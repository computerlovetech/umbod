import json
from typing import Any

import pytest
from fastmcp.tools import ToolResult
from mcp.shared.exceptions import MCPError
from mcp.types import TextContent

from umbod.core.responses import (
    OperationState,
    RetryAdvice,
    ToolArgumentIssue,
    ToolErrorDetails,
    ToolNotice,
    ToolResponseMetadataFactory,
)
from umbod.mcp.responses.adapter import RESPONSE_METADATA_KEY, BuiltinToolResponseAdapter
from umbod.mcp.responses.rendering import render_response_guidance, serialized_payload_content


@pytest.mark.parametrize("state", list(OperationState))
def test_failure_text_projects_every_recovery_instruction_and_issue(
    state: OperationState,
) -> None:
    metadata = ToolResponseMetadataFactory("release", "revision").failure(
        "request-reference",
        error=ToolErrorDetails(
            code="invalid_arguments", message="Correct the arguments.",
            issues=(ToolArgumentIssue(field="value", reason="invalid_type", correction="Provide an integer."),),
        ),
        operation_state=state, retry=RetryAdvice.INSPECT_BEFORE_RETRY,
        instructions=("Inspect the original destination.",),
        notices=(ToolNotice(code="limited_inspection", message="Inspection may be incomplete."),),
    )

    rendered = "\n".join(block.text for block in render_response_guidance(metadata))

    assert "Outcome: failure" in rendered
    assert f"Operation state: {state}" in rendered
    assert metadata.guidance.recovery.retry in rendered
    assert metadata.guidance.error.code in rendered
    assert metadata.guidance.error.message in rendered
    for issue in metadata.guidance.error.issues:
        assert issue.field in rendered
        assert issue.correction in rendered
    for instruction in metadata.guidance.recovery.instructions:
        assert instruction in rendered
    for notice in metadata.guidance.notices:
        assert notice.code in rendered
        assert notice.message in rendered
    assert "request-reference" in rendered
    assert "release" in rendered
    assert "revision" in rendered


def test_success_notice_and_outcome_are_model_visible() -> None:
    metadata = ToolResponseMetadataFactory("release", "revision").success(
        "request-reference",
        notices=(ToolNotice(code="partial_result", message="Only authorized entries are included."),),
    )

    rendered = "\n".join(block.text for block in render_response_guidance(metadata))

    assert "Outcome: success. Operation state: completed." in rendered
    assert "Retry advice: not_needed." in rendered
    assert "partial_result" in rendered
    assert "Only authorized entries are included." in rendered


@pytest.mark.parametrize("text", ['{"value":4}', '{ "value": 4 }'])
def test_existing_serialized_success_payload_is_not_duplicated(text: str) -> None:
    assert serialized_payload_content([TextContent(type="text", text=text)], {"value": 4}) == []


@pytest.mark.parametrize("text", ["Human-readable result.", '{"value": true}', "null", "NaN"])
def test_missing_or_different_serialized_success_payload_is_added(text: str) -> None:
    blocks = serialized_payload_content([TextContent(type="text", text=text)], {"value": 1})

    assert len(blocks) == 1
    assert json.loads(blocks[0].text) == {"value": 1}


@pytest.mark.asyncio
async def test_client_metadata_is_preserved_without_becoming_guidance(
    adapter: BuiltinToolResponseAdapter,
) -> None:
    original = ToolResult(
        content="Approved result.", structured_content={"value": 4},
        meta={"vendor": {"private_client_marker": "client-only-value"}},
    )

    async def invoke(arguments: dict[str, Any]) -> ToolResult:
        return original

    result = await adapter.invoke(invoke, {})
    visible = "\n".join(block.text for block in result.content if isinstance(block, TextContent))

    assert result.meta["vendor"] == original.meta["vendor"]
    assert "private_client_marker" not in visible
    assert "client-only-value" not in visible
    assert "Outcome: success" in visible
    assert result.structured_content == original.structured_content


@pytest.mark.asyncio
async def test_native_protocol_error_passes_through_by_identity(
    adapter: BuiltinToolResponseAdapter,
) -> None:
    error = MCPError(code=-32602, message="Protocol rejection.")

    async def invoke(arguments: dict[str, Any]) -> ToolResult:
        raise error

    with pytest.raises(MCPError) as caught:
        await adapter.invoke(invoke, {})

    assert caught.value is error


@pytest.mark.asyncio
async def test_payload_serialization_failure_retains_completion_and_does_not_repeat_execution(
    adapter: BuiltinToolResponseAdapter,
) -> None:
    executions: list[str] = []

    async def invoke(arguments: dict[str, Any]) -> ToolResult:
        executions.append("completed")
        return ToolResult(structured_content={"value": 4}).model_copy(
            update={"structured_content": {"unserializable": object()}},
        )

    result = await adapter.invoke(invoke, {})
    guidance = result.meta[RESPONSE_METADATA_KEY]["guidance"]
    visible = "\n".join(block.text for block in result.content if isinstance(block, TextContent))

    assert executions == ["completed"]
    assert result.is_error
    assert result.structured_content is None
    assert guidance["operation_state"] == "completed"
    assert guidance["recovery"]["retry"] == "inspect_before_retry"
    assert "Do not retry automatically" in visible
    for instruction in guidance["recovery"]["instructions"]:
        assert instruction in visible


@pytest.mark.asyncio
async def test_general_renderer_failure_uses_independent_safe_failure_projection(
    adapter: BuiltinToolResponseAdapter, monkeypatch: pytest.MonkeyPatch,
) -> None:
    executions: list[str] = []

    def fail_rendering(*arguments: object, **options: object) -> list[TextContent]:
        raise ValueError("SECRET renderer payload")

    async def invoke(arguments: dict[str, Any]) -> ToolResult:
        executions.append("completed")
        return ToolResult(structured_content={"value": 4})

    monkeypatch.setattr("umbod.mcp.responses.adapter.render_response_guidance", fail_rendering)
    result = await adapter.invoke(invoke, {})
    guidance = result.meta[RESPONSE_METADATA_KEY]["guidance"]
    serialized = json.dumps(result.to_mcp_result().model_dump(mode="json"))

    assert executions == ["completed"]
    assert result.is_error
    assert guidance["operation_state"] == "completed"
    assert guidance["recovery"]["retry"] == "inspect_before_retry"
    assert "Do not retry automatically" in serialized
    assert "SECRET" not in serialized
    assert "renderer payload" not in serialized
