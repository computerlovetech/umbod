import asyncio

from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import Generic, Protocol, TypeAlias, TypeVar

ExecutionRequest = TypeVar("ExecutionRequest")
ExecutionContext = TypeVar("ExecutionContext")
InterceptorRequest = TypeVar("InterceptorRequest", contravariant=True)
InterceptorContext = TypeVar("InterceptorContext", contravariant=True)
ExecutionResult = TypeVar("ExecutionResult")


@dataclass(frozen=True)
class PreparedExecution(Generic[ExecutionContext, ExecutionResult]):
    context: ExecutionContext
    operation: Callable[[], Awaitable[ExecutionResult]]


@dataclass(frozen=True)
class ToolExecutionSucceeded:
    result: object


@dataclass(frozen=True)
class ToolExecutionFailed:
    error: BaseException


ToolExecutionOutcome: TypeAlias = ToolExecutionSucceeded | ToolExecutionFailed


class OrderedToolExecutionInterceptor(Protocol[InterceptorRequest, InterceptorContext]):
    async def before_tool_preparation(self, request: InterceptorRequest) -> object: ...

    async def before_tool_execution(
        self,
        context: InterceptorContext,
        state: object,
    ) -> None: ...

    async def after_tool_execution(
        self,
        request: InterceptorRequest,
        outcome: ToolExecutionOutcome,
        state: object,
    ) -> None: ...


class OrderedExecutionRunner(Generic[ExecutionRequest, ExecutionContext, ExecutionResult]):
    def __init__(self, interceptors: Sequence[OrderedToolExecutionInterceptor[ExecutionRequest, ExecutionContext]]) -> None:
        self._interceptors = tuple(interceptors)

    async def execute(
        self,
        request: ExecutionRequest,
        prepare: Callable[[], Awaitable[PreparedExecution[ExecutionContext, ExecutionResult]]],
    ) -> ExecutionResult:
        entered_interceptors: list[tuple[OrderedToolExecutionInterceptor[ExecutionRequest, ExecutionContext], object]] = []
        try:
            await self._enter_interceptors(request, entered_interceptors)
            prepared = await prepare()
            await self._run_before_execution(entered_interceptors, prepared.context)
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

    async def _enter_interceptors(
        self,
        request: ExecutionRequest,
        entered_interceptors: list[tuple[OrderedToolExecutionInterceptor[ExecutionRequest, ExecutionContext], object]],
    ) -> None:
        for interceptor in self._interceptors:
            state = await interceptor.before_tool_preparation(request)
            entered_interceptors.append((interceptor, state))

    async def _run_before_execution(
        self,
        entered_interceptors: Sequence[tuple[OrderedToolExecutionInterceptor[ExecutionRequest, ExecutionContext], object]],
        context: ExecutionContext,
    ) -> None:
        for interceptor, state in entered_interceptors:
            await interceptor.before_tool_execution(context, state)

    async def _run_after_interceptors(
        self,
        entered_interceptors: Sequence[tuple[OrderedToolExecutionInterceptor[ExecutionRequest, ExecutionContext], object]],
        request: ExecutionRequest,
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
