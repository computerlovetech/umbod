from dataclasses import dataclass

import pytest

from umbod.core.invocation.failure_evidence import (
    InvocationFailureOrigin,
    capture_returned_failure,
    current_invocation_failure,
    invocation_failure_scope,
)
from umbod.core.invocation.tools.ordered_execution import (
    OrderedExecutionRunner,
    PreparedExecution,
    ToolExecutionOutcome,
    ToolExecutionSucceeded,
)


@dataclass(frozen=True)
class CalculationRequest:
    quantity: int


class CalculationInterceptor:
    def __init__(self, events: list[object]) -> None:
        self._events = events

    async def before_tool_preparation(self, request: CalculationRequest) -> object:
        self._events.append(("requested", request.quantity))
        return request.quantity

    async def before_tool_execution(self, context: int, state: object) -> None:
        self._events.append(("prepared", context, state))

    async def after_tool_execution(
        self, request: CalculationRequest, outcome: ToolExecutionOutcome, state: object
    ) -> None:
        self._events.append(("finished", request.quantity, outcome, state))


@pytest.mark.asyncio
async def test_ordered_pipeline_runs_with_a_calculation_request_and_context() -> None:
    events: list[object] = []
    request = CalculationRequest(quantity=3)
    pipeline = OrderedExecutionRunner[CalculationRequest, int, int](
        (CalculationInterceptor(events),)
    )

    async def prepare() -> PreparedExecution[int, int]:
        total = request.quantity * 4

        async def operation() -> int:
            events.append(("calculated", total))
            return total

        return PreparedExecution(context=total, operation=operation)

    result = await pipeline.execute(request, prepare)

    assert result == 12
    assert events == [
        ("requested", 3),
        ("prepared", 12, 3),
        ("calculated", 12),
        ("finished", 3, ToolExecutionSucceeded(12), 3),
    ]


@pytest.mark.asyncio
async def test_runner_preserves_failure_evidence_for_the_enclosing_invocation() -> None:
    runner = OrderedExecutionRunner[CalculationRequest, int, str](())

    async def prepare() -> PreparedExecution[int, str]:
        async def operation() -> str:
            capture_returned_failure(InvocationFailureOrigin.INTERNAL)
            return "failed"

        return PreparedExecution(context=0, operation=operation)

    with invocation_failure_scope():
        assert await runner.execute(CalculationRequest(quantity=0), prepare) == "failed"
        evidence = current_invocation_failure()
        assert evidence is not None
        assert evidence.origin is InvocationFailureOrigin.INTERNAL
