from asyncio import CancelledError
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from types import CodeType
from uuid import uuid4

import mcp.types as mt
from fastmcp.exceptions import AuthorizationError, DisabledError, NotFoundError, PromptError, ValidationError
from fastmcp.prompts.function_prompt import FunctionPrompt
from fastmcp.prompts.base import Prompt, PromptResult
from fastmcp.resources.base import Resource, ResourceResult
from fastmcp.resources.template import ResourceTemplate
from fastmcp.server.middleware import CallNext, Middleware, MiddlewareContext
from pydantic import ValidationError as PydanticValidationError

from umbod.core.invocation.failure_evidence import InvocationExceptionEvidence, InvocationFailureOrigin, InvocationRejectedFailure, exception_evidence
from umbod.core.signals import SignalFailureHandler, SignalPublisher
from umbod.http_metadata import current_request_id
from umbod.mcp.logging.audit.identity import McpAuditIdentitySource
from umbod.mcp.signals.capabilities import (
    McpCapabilityCancelled, McpCapabilityCompleted, McpCapabilityDiscoveryTarget,
    McpCapabilityFailed, McpCapabilityFailureCategory, McpCapabilityMethod,
    McpCapabilityResult, McpCapabilitySucceeded, McpCapabilityTarget,
    prompt_target, resource_target,
)
from umbod.mcp.signals.context import current_mcp_invocation_context
from umbod.mcp.signals.events import McpInvocationActor, McpInvocationCorrelation


@dataclass(frozen=True)
class _Observation:
    method: McpCapabilityMethod
    target: McpCapabilityTarget
    actor: McpInvocationActor
    correlation: McpInvocationCorrelation
    started_at_unix_nano: int
    started_monotonic: float


class McpCapabilityCompletionMiddleware(Middleware):
    def __init__(
        self,
        publisher: SignalPublisher[McpCapabilityCompleted],
        identity_source: McpAuditIdentitySource,
        failure_handler: SignalFailureHandler,
        clock: Callable[[], float],
        timestamp_clock: Callable[[], int],
    ) -> None:
        self._publisher = publisher
        self._identity_source = identity_source
        self._failure_handler = failure_handler
        self._clock = clock
        self._timestamp_clock = timestamp_clock

    async def on_read_resource(
        self,
        context: MiddlewareContext[mt.ReadResourceRequestParams],
        call_next: CallNext[mt.ReadResourceRequestParams, ResourceResult],
    ) -> ResourceResult:
        return await self._observe(McpCapabilityMethod.READ_RESOURCE, context, call_next)

    async def on_get_prompt(
        self,
        context: MiddlewareContext[mt.GetPromptRequestParams],
        call_next: CallNext[mt.GetPromptRequestParams, PromptResult],
    ) -> PromptResult:
        return await self._observe(McpCapabilityMethod.GET_PROMPT, context, call_next)

    async def on_list_resources(
        self,
        context: MiddlewareContext[mt.ListResourcesRequest],
        call_next: CallNext[mt.ListResourcesRequest, Sequence[Resource]],
    ) -> Sequence[Resource]:
        return await self._observe(McpCapabilityMethod.LIST_RESOURCES, context, call_next)

    async def on_list_resource_templates(
        self,
        context: MiddlewareContext[mt.ListResourceTemplatesRequest],
        call_next: CallNext[mt.ListResourceTemplatesRequest, Sequence[ResourceTemplate]],
    ) -> Sequence[ResourceTemplate]:
        return await self._observe(McpCapabilityMethod.LIST_RESOURCE_TEMPLATES, context, call_next)

    async def on_list_prompts(
        self,
        context: MiddlewareContext[mt.ListPromptsRequest],
        call_next: CallNext[mt.ListPromptsRequest, Sequence[Prompt]],
    ) -> Sequence[Prompt]:
        return await self._observe(McpCapabilityMethod.LIST_PROMPTS, context, call_next)

    async def _observe[T, R](
        self, method: McpCapabilityMethod, context: MiddlewareContext[T], call_next: CallNext[T, R],
    ) -> R:
        try:
            observation = self._start(method, context)
        except Exception as error:
            self._report_failure(error)
            return await call_next(context)
        try:
            result = await call_next(context)
        except CancelledError as error:
            self._finish_failure(observation, error)
            raise
        except Exception as error:
            self._finish_failure(observation, error)
            raise
        self._finish(observation, McpCapabilitySucceeded())
        return result

    def _start[T](self, method: McpCapabilityMethod, context: MiddlewareContext[T]) -> _Observation:
        invocation = current_mcp_invocation_context()
        correlation = invocation.correlation if invocation is not None else McpInvocationCorrelation(
            trace_id=current_request_id() or uuid4().hex,
        )
        return _Observation(
            method=method,
            target=_target(context.message),
            actor=self._identity_source.invocation_actor(context.fastmcp_context),
            correlation=correlation,
            started_at_unix_nano=self._timestamp_clock(),
            started_monotonic=self._clock(),
        )

    def _finish_failure(self, observation: _Observation, error: BaseException) -> None:
        try:
            if isinstance(error, CancelledError):
                result: McpCapabilityResult = McpCapabilityCancelled(_bounded_evidence(error))
            else:
                category = _failure_category(error)
                evidence = (
                    _bounded_evidence(error)
                    if category == McpCapabilityFailureCategory.UNEXPECTED_ERROR
                    else InvocationRejectedFailure(InvocationFailureOrigin.CLIENT_INPUT)
                )
                result = McpCapabilityFailed(category, evidence)
            self._finish(observation, result)
        except Exception as observation_error:
            self._report_failure(observation_error)

    def _finish(self, observation: _Observation, result: McpCapabilityResult) -> None:
        try:
            self._publisher.send(McpCapabilityCompleted(
                method=observation.method,
                target=observation.target,
                result=result,
                duration_ms=max(0.0, (self._clock() - observation.started_monotonic) * 1000),
                correlation=observation.correlation,
                actor=observation.actor,
                started_at_unix_nano=observation.started_at_unix_nano,
            ))
        except Exception as error:
            self._report_failure(error)

    def _report_failure(self, error: Exception) -> None:
        try:
            self._failure_handler.handles("mcp.capability.logging", error)
        except Exception:
            return


def _target(message: object) -> McpCapabilityTarget:
    if isinstance(message, mt.ReadResourceRequestParams):
        return resource_target(str(message.uri))
    if isinstance(message, mt.GetPromptRequestParams):
        return prompt_target(message.name)
    return McpCapabilityDiscoveryTarget()


def _failure_category(error: BaseException) -> McpCapabilityFailureCategory:
    if isinstance(error, AuthorizationError):
        return McpCapabilityFailureCategory.AUTHORIZATION
    if isinstance(error, (ValidationError, PydanticValidationError)) or _prompt_argument_rejection(error):
        return McpCapabilityFailureCategory.VALIDATION
    if isinstance(error, (NotFoundError, DisabledError)):
        return McpCapabilityFailureCategory.NOT_FOUND
    return McpCapabilityFailureCategory.UNEXPECTED_ERROR


def _prompt_argument_rejection(error: BaseException) -> bool:
    seen: set[int] = set()
    while isinstance(error, PromptError) and error.__cause__ is not None and id(error) not in seen:
        if _raised_by(error, FunctionPrompt._convert_string_arguments.__code__):
            return isinstance(error.__cause__, (ValueError, TypeError, PydanticValidationError))
        seen.add(id(error))
        error = error.__cause__
    return isinstance(error, (ValueError, PydanticValidationError)) and _raised_by(error, FunctionPrompt.render.__code__)


def _raised_by(error: BaseException, code: CodeType) -> bool:
    traceback = error.__traceback__
    if traceback is None:
        return False
    while traceback.tb_next is not None:
        traceback = traceback.tb_next
    return traceback.tb_frame.f_code is code


def _bounded_evidence(error: BaseException) -> InvocationExceptionEvidence:
    evidence = exception_evidence(error, InvocationFailureOrigin.INTERNAL)
    return InvocationExceptionEvidence(
        origin=evidence.origin,
        exception_type=evidence.exception_type[:4096],
        stacktrace=evidence.stacktrace[:4096],
    )
