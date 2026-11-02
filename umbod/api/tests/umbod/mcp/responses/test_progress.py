import asyncio
from typing import Any

import pytest
from fastmcp.tools import ToolResult

from umbod.core.responses import OperationState
from umbod.mcp.responses.adapter import (
    RESPONSE_METADATA_KEY,
    BuiltinToolResponseAdapter,
)
from umbod.mcp.responses.progress import (
    operation_completed,
    operation_progress_context,
    operation_started,
)


def test_nested_progress_scopes_restore_outer_state() -> None:
    with operation_progress_context() as outer:
        operation_started()
        with operation_progress_context() as inner:
            assert inner.state == OperationState.NOT_STARTED
            operation_completed()
            assert inner.state == OperationState.COMPLETED
        assert outer.state == OperationState.UNKNOWN
        operation_completed()
        assert outer.state == OperationState.COMPLETED
    with operation_progress_context() as fresh:
        assert fresh.state == OperationState.NOT_STARTED


@pytest.mark.asyncio
async def test_nested_adapter_invocations_do_not_complete_the_outer_operation(
    adapter: BuiltinToolResponseAdapter,
) -> None:
    inner_results: list[ToolResult] = []

    async def inner(arguments: dict[str, Any]) -> ToolResult:
        operation_completed()
        return ToolResult(content="inner complete")

    async def outer(arguments: dict[str, Any]) -> ToolResult:
        operation_started()
        inner_results.append(await adapter.invoke(inner, {}))
        raise RuntimeError("outer failed")

    result = await adapter.invoke(outer, {})

    assert (
        inner_results[0].meta[RESPONSE_METADATA_KEY]["guidance"]["operation_state"] == "completed"
    )
    assert result.meta[RESPONSE_METADATA_KEY]["guidance"]["operation_state"] == "unknown"


@pytest.mark.asyncio
async def test_concurrent_invocations_have_isolated_progress(
    adapter: BuiltinToolResponseAdapter,
) -> None:
    completed = asyncio.Event()
    started = asyncio.Event()

    async def completed_body(arguments: dict[str, Any]) -> ToolResult:
        operation_completed()
        completed.set()
        await started.wait()
        raise RuntimeError("completed failure")

    async def started_body(arguments: dict[str, Any]) -> ToolResult:
        await completed.wait()
        operation_started()
        started.set()
        raise RuntimeError("started failure")

    first, second = await asyncio.gather(
        adapter.invoke(completed_body, {}), adapter.invoke(started_body, {})
    )

    assert first.meta[RESPONSE_METADATA_KEY]["guidance"]["operation_state"] == "completed"
    assert second.meta[RESPONSE_METADATA_KEY]["guidance"]["operation_state"] == "unknown"
    with operation_progress_context() as fresh:
        assert fresh.state == OperationState.NOT_STARTED


def test_progress_markers_outside_invocation_do_not_leak_into_new_scope() -> None:
    operation_started()
    operation_completed()

    with operation_progress_context() as progress:
        assert progress.state == OperationState.NOT_STARTED
