import asyncio
from typing import Any

import pytest

from umbod.core.capabilities import CapabilityIdentity
from umbod.core.invocation.tools.execution import OrderedToolExecutionPipeline, PreparedToolExecution, ToolExecutionContext, ToolExecutionOutcome, ToolExecutionPipeline, ToolExecutionRequest, ToolExecutionSucceeded


class RecordingInterceptor:
    def __init__(self, name: str, events: list[str]) -> None:
        self._name = name
        self._events = events

    async def before_tool_preparation(self, request: ToolExecutionRequest) -> object:
        self._events.append(f"prepare:{self._name}")
        return self._name

    async def before_tool_execution(
        self,
        context: ToolExecutionContext,
        state: object,
    ) -> None:
        self._events.append(f"before:{self._name}")

    async def after_tool_execution(
        self,
        request: ToolExecutionRequest,
        outcome: ToolExecutionOutcome,
        state: object,
    ) -> None:
        outcome_name = "success" if isinstance(outcome, ToolExecutionSucceeded) else "failure"
        self._events.append(f"after:{self._name}:{outcome_name}")


class CancellingAfterInterceptor(RecordingInterceptor):
    async def after_tool_execution(
        self,
        request: ToolExecutionRequest,
        outcome: ToolExecutionOutcome,
        state: object,
    ) -> None:
        raise asyncio.CancelledError


class InvocationRecordingInterceptor:
    def __init__(self) -> None:
        self.arguments: dict[str, Any] = {}

    async def before_tool_preparation(self, request: ToolExecutionRequest) -> object:
        return None

    async def before_tool_execution(
        self,
        context: ToolExecutionContext,
        state: object,
    ) -> None:
        self.arguments = dict(context.invocation.arguments)

    async def after_tool_execution(
        self,
        request: ToolExecutionRequest,
        outcome: ToolExecutionOutcome,
        state: object,
    ) -> None:
        return None


class RejectingInterceptor:
    async def before_tool_preparation(self, request: ToolExecutionRequest) -> object:
        return None

    async def before_tool_execution(
        self,
        context: ToolExecutionContext,
        state: object,
    ) -> None:
        raise PermissionError("rejected")

    async def after_tool_execution(
        self,
        request: ToolExecutionRequest,
        outcome: ToolExecutionOutcome,
        state: object,
    ) -> None:
        return None


def _request() -> ToolExecutionRequest:
    return ToolExecutionRequest(
        identity=CapabilityIdentity(
            connector_kind="native",
            connector_id="slack",
            capability_kind="tool",
            capability_key="search_messages",
        ),
        public_tool_name="slack_search_messages",
        arguments={"query": "release"},
    )


async def _execute_through_port(
    pipeline: ToolExecutionPipeline[dict[str, Any]],
    events: list[str],
) -> dict[str, Any]:
    request = _request()

    async def prepare() -> PreparedToolExecution[dict[str, Any]]:
        events.append("preparation")

        async def operation() -> dict[str, Any]:
            events.append("operation")
            return {"ok": True}

        return PreparedToolExecution(
            arguments=request.arguments,
            operation=operation,
            invocation_arguments=request.arguments,
        )

    return await pipeline.execute(request, prepare)


@pytest.mark.asyncio
async def test_pipeline_covers_preparation_and_ordered_execution() -> None:
    events: list[str] = []
    pipeline = OrderedToolExecutionPipeline[dict[str, Any]](
        (
            RecordingInterceptor("policy", events),
            RecordingInterceptor("audit", events),
        )
    )

    result = await _execute_through_port(pipeline, events)

    assert result == {"ok": True}
    assert events == [
        "prepare:policy",
        "prepare:audit",
        "preparation",
        "before:policy",
        "before:audit",
        "operation",
        "after:audit:success",
        "after:policy:success",
    ]


@pytest.mark.asyncio
async def test_pipeline_uses_distinct_invocation_arguments() -> None:
    interceptor = InvocationRecordingInterceptor()
    pipeline = OrderedToolExecutionPipeline[dict[str, Any]]((interceptor,))
    request = _request()

    async def prepare() -> PreparedToolExecution[dict[str, Any]]:
        async def operation() -> dict[str, Any]:
            return {"ok": True}

        return PreparedToolExecution(
            arguments={"file": b"private-bytes"},
            invocation_arguments={"file": {"filename": "image.png", "sha256": "digest"}},
            operation=operation,
        )

    await pipeline.execute(request, prepare)

    assert interceptor.arguments == {
        "file": {"filename": "image.png", "sha256": "digest"}
    }


@pytest.mark.asyncio
async def test_pipeline_stops_before_operation_when_an_interceptor_rejects() -> None:
    events: list[str] = []
    pipeline = OrderedToolExecutionPipeline[dict[str, Any]]((RejectingInterceptor(),))

    with pytest.raises(PermissionError, match="rejected"):
        await _execute_through_port(pipeline, events)

    assert events == ["preparation"]


@pytest.mark.asyncio
async def test_pipeline_unwinds_interceptors_when_preparation_fails() -> None:
    events: list[str] = []
    pipeline = OrderedToolExecutionPipeline[dict[str, Any]](
        (RecordingInterceptor("audit", events),)
    )
    request = _request()

    async def failing_preparation() -> PreparedToolExecution[dict[str, Any]]:
        events.append("preparation")
        raise ValueError("invalid arguments")

    with pytest.raises(ValueError, match="invalid arguments"):
        await pipeline.execute(request, failing_preparation)

    assert events == ["prepare:audit", "preparation", "after:audit:failure"]


@pytest.mark.asyncio
async def test_pipeline_unwinds_interceptors_when_operation_fails() -> None:
    events: list[str] = []
    pipeline = OrderedToolExecutionPipeline[dict[str, Any]](
        (
            RecordingInterceptor("policy", events),
            RecordingInterceptor("audit", events),
        )
    )
    request = _request()

    async def prepare() -> PreparedToolExecution[dict[str, Any]]:
        async def failing_operation() -> dict[str, Any]:
            events.append("operation")
            raise RuntimeError("failed")

        return PreparedToolExecution(
            arguments=request.arguments,
            operation=failing_operation,
            invocation_arguments=request.arguments,
        )

    with pytest.raises(RuntimeError, match="failed"):
        await pipeline.execute(request, prepare)

    assert events == [
        "prepare:policy",
        "prepare:audit",
        "before:policy",
        "before:audit",
        "operation",
        "after:audit:failure",
        "after:policy:failure",
    ]


@pytest.mark.asyncio
async def test_pipeline_does_not_swallow_cancellation_during_failure_unwind() -> None:
    events: list[str] = []
    pipeline = OrderedToolExecutionPipeline[dict[str, Any]](
        (
            RecordingInterceptor("telemetry", events),
            CancellingAfterInterceptor("cleanup", events),
        )
    )
    request = _request()

    async def prepare() -> PreparedToolExecution[dict[str, Any]]:
        async def failing_operation() -> dict[str, Any]:
            raise RuntimeError("failed")

        return PreparedToolExecution(
            arguments=request.arguments,
            operation=failing_operation,
            invocation_arguments=request.arguments,
        )

    with pytest.raises(asyncio.CancelledError):
        await pipeline.execute(request, prepare)

    assert events == [
        "prepare:telemetry",
        "prepare:cleanup",
        "before:telemetry",
        "before:cleanup",
        "after:telemetry:failure",
    ]
