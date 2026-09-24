import asyncio

from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Generic, Protocol, TypeAlias, TypeVar

from umbod.core.capabilities import CapabilityIdentity
from umbod.core.invocation.policy import (
    ConnectorInvocation,
    ConnectorInvocationDenied,
    ConnectorInvocationPolicy,
    evaluate_direct_invocation,
)


ExecutionResult = TypeVar("ExecutionResult")


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


@dataclass(frozen=True)
class ToolExecutionSucceeded:
    result: object


@dataclass(frozen=True)
class ToolExecutionFailed:
    error: BaseException


ToolExecutionOutcome: TypeAlias = ToolExecutionSucceeded | ToolExecutionFailed


class ToolExecutionInterceptor(Protocol):
    async def before_tool_preparation(self, request: ToolExecutionRequest) -> object: ...

    async def before_tool_execution(
        self,
        context: ToolExecutionContext,
        state: object,
    ) -> None: ...

    async def after_tool_execution(
        self,
        request: ToolExecutionRequest,
        outcome: ToolExecutionOutcome,
        state: object,
    ) -> None: ...


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
        self._interceptors = tuple(interceptors)

    async def execute(
        self,
        request: ToolExecutionRequest,
        prepare: Callable[[], Awaitable[PreparedToolExecution[ExecutionResult]]],
    ) -> ExecutionResult:
        entered_interceptors: list[tuple[ToolExecutionInterceptor, object]] = []
        try:
            await self._enter_interceptors(request, entered_interceptors)
            prepared = await prepare()
            invocation = self._create_invocation(request, prepared)
            await self._run_before_execution(
                entered_interceptors,
                ToolExecutionContext(request=request, invocation=invocation),
            )
            result = await prepared.operation()
        except BaseException as error:
            await self._run_after_interceptors(
                entered_interceptors,
                request,
                ToolExecutionFailed(error),
                suppress_failures=True,
            )
            raise
        await self._run_after_interceptors(
            entered_interceptors,
            request,
            ToolExecutionSucceeded(result),
            suppress_failures=False,
        )
        return result

    def _create_invocation(
        self,
        request: ToolExecutionRequest,
        prepared: PreparedToolExecution[ExecutionResult],
    ) -> ConnectorInvocation:
        return ConnectorInvocation.create(
            connector_kind=request.identity.connector_kind,
            connector_id=request.identity.connector_id,
            operation_name=request.identity.capability_key,
            public_tool_name=request.public_tool_name,
            arguments=prepared.invocation_arguments,
        )

    async def _enter_interceptors(
        self,
        request: ToolExecutionRequest,
        entered_interceptors: list[tuple[ToolExecutionInterceptor, object]],
    ) -> None:
        for interceptor in self._interceptors:
            state = await interceptor.before_tool_preparation(request)
            entered_interceptors.append((interceptor, state))

    async def _run_before_execution(
        self,
        entered_interceptors: Sequence[tuple[ToolExecutionInterceptor, object]],
        context: ToolExecutionContext,
    ) -> None:
        for interceptor, state in entered_interceptors:
            await interceptor.before_tool_execution(context, state)

    async def _run_after_interceptors(
        self,
        entered_interceptors: Sequence[tuple[ToolExecutionInterceptor, object]],
        request: ToolExecutionRequest,
        outcome: ToolExecutionOutcome,
        suppress_failures: bool,
    ) -> None:
        errors: list[BaseException] = []
        for interceptor, state in reversed(entered_interceptors):
            try:
                await interceptor.after_tool_execution(request, outcome, state)
            except BaseException as error:
                errors.append(error)
        cancellation = next(
            (error for error in errors if isinstance(error, asyncio.CancelledError)),
            None,
        )
        if cancellation is not None:
            raise cancellation
        if errors and not suppress_failures:
            raise errors[0]


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
