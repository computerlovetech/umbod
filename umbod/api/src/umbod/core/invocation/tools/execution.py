import asyncio

from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Generic, Protocol, TypeAlias

from umbod.core.capabilities import CapabilityIdentity
from umbod.core.invocation.failure_evidence import invocation_failure_scope
from umbod.core.invocation.policy import (
    ConnectorInvocation,
    ConnectorInvocationDenied,
    ConnectorInvocationPolicy,
    evaluate_direct_invocation,
)
from umbod.core.invocation.tools.ordered_execution import (
    ExecutionResult,
    OrderedToolExecutionInterceptor,
    OrderedExecutionRunner,
    PreparedExecution,
    ToolExecutionFailed as ToolExecutionFailed,
    ToolExecutionOutcome as ToolExecutionOutcome,
    ToolExecutionSucceeded as ToolExecutionSucceeded,
)


@dataclass(frozen=True)
class ToolExecutionRequest:
    identity: CapabilityIdentity
    public_tool_name: str
    arguments: Mapping[str, Any]


@dataclass(frozen=True)
class ToolExecutionContext:
    request: ToolExecutionRequest
    invocation: ConnectorInvocation


@dataclass(frozen=True)
class PreparedToolExecution(Generic[ExecutionResult]):
    arguments: Mapping[str, Any]
    operation: Callable[[], Awaitable[ExecutionResult]]
    invocation_arguments: Mapping[str, Any]


ToolExecutionInterceptor: TypeAlias = OrderedToolExecutionInterceptor[
    ToolExecutionRequest, ToolExecutionContext
]


def prepare_tool_execution(
    validated_arguments: Mapping[str, Any],
    operation: Callable[[], Awaitable[ExecutionResult]],
    invocation_arguments: Mapping[str, Any],
) -> PreparedToolExecution[ExecutionResult]:
    return PreparedToolExecution(
        arguments=validated_arguments,
        operation=operation,
        invocation_arguments=invocation_arguments,
    )


class ToolExecutionPipeline(Protocol, Generic[ExecutionResult]):
    async def execute(
        self,
        request: ToolExecutionRequest,
        prepare: Callable[[], Awaitable[PreparedToolExecution[ExecutionResult]]],
    ) -> ExecutionResult: ...


class OrderedToolExecutionPipeline(Generic[ExecutionResult]):
    def __init__(self, interceptors: Sequence[ToolExecutionInterceptor]) -> None:
        self._ordered_pipeline = OrderedExecutionRunner[
            ToolExecutionRequest, ToolExecutionContext, ExecutionResult
        ](interceptors)

    async def execute(
        self,
        request: ToolExecutionRequest,
        prepare: Callable[[], Awaitable[PreparedToolExecution[ExecutionResult]]],
    ) -> ExecutionResult:
        async def prepare_connector_execution() -> PreparedExecution[
            ToolExecutionContext, ExecutionResult
        ]:
            prepared = await prepare()
            invocation = ConnectorInvocation.create(
                connector_kind=request.identity.connector_kind,
                connector_id=request.identity.connector_id,
                operation_name=request.identity.capability_key,
                public_tool_name=request.public_tool_name,
                arguments=prepared.invocation_arguments,
            )
            return PreparedExecution(
                context=ToolExecutionContext(request=request, invocation=invocation),
                operation=prepared.operation,
            )

        with invocation_failure_scope():
            return await self._ordered_pipeline.execute(request, prepare_connector_execution)


class InvocationPolicyToolExecutionInterceptor:
    def __init__(self, invocation_policy: ConnectorInvocationPolicy) -> None:
        self._invocation_policy = invocation_policy

    async def before_tool_preparation(self, request: ToolExecutionRequest) -> object:
        return None

    async def before_tool_execution(
        self,
        context: ToolExecutionContext,
        state: object,
    ) -> None:
        try:
            await evaluate_direct_invocation(self._invocation_policy, context.invocation)
        except asyncio.CancelledError:
            raise
        except ConnectorInvocationDenied:
            raise
        except Exception as error:
            raise RuntimeError("Connector invocation policy failed") from error

    async def after_tool_execution(
        self,
        request: ToolExecutionRequest,
        outcome: ToolExecutionOutcome,
        state: object,
    ) -> None:
        return None


def create_tool_execution_pipeline(
    invocation_policy: ConnectorInvocationPolicy,
    interceptors: Sequence[ToolExecutionInterceptor],
) -> ToolExecutionPipeline[ExecutionResult]:
    return OrderedToolExecutionPipeline[ExecutionResult](
        (*interceptors, InvocationPolicyToolExecutionInterceptor(invocation_policy))
    )
