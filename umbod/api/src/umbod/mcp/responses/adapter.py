import asyncio
from typing import Any
from uuid import uuid4

from fastmcp.exceptions import AuthorizationError, ValidationError
from fastmcp.tools import InputRequiredToolResult, ToolResult
from fastmcp.tools.base import Tool
from mcp.shared.exceptions import MCPError
from mcp.types import CallToolResult
from pydantic import ValidationError as ModelValidationError

from umbod.core.responses import (
    OperationState, RetryAdvice, ToolErrorDetails, ToolFailureMetadata, ToolNotice, ToolResponseMetadata,
    ToolResponseMetadataFactory,
)
from umbod.http_metadata import current_request_id, request_id_context
from umbod.mcp.tools.errors import (
    BuiltinToolArgumentError, BuiltinToolAuthorizationDenied, BuiltinToolError,
    ToolAuthorizationDenied, ToolResponseContractError,
)

from .arguments import argument_diagnostics, argument_notices, generic_correction
from .ports import ToolInvocation
from .progress import operation_completed, operation_progress_context, operation_state
from .recovery import recovery_instructions
from .rendering import render_failure_guidance, render_response_guidance, serialized_payload_content


RESPONSE_METADATA_KEY = "computerlove.tech/umbod"


class BuiltinToolResult(ToolResult):
    pass


class UnmodifiedToolResponseAdapter:
    async def invoke(self, invocation: ToolInvocation, arguments: dict[str, Any]) -> ToolResult:
        return await invocation(arguments)

    def prepare(self, result: ToolResult, arguments: dict[str, Any]) -> ToolResult:
        return result

    def completed(self) -> None:
        pass


class BuiltinToolResponseAdapter:
    def __init__(self, factory: ToolResponseMetadataFactory, tool: Tool) -> None:
        self._factory = factory
        self._tool = tool

    async def invoke(self, invocation: ToolInvocation, arguments: dict[str, Any]) -> ToolResult:
        request_id = current_request_id() or uuid4().hex
        with request_id_context(request_id), operation_progress_context() as progress:
            try:
                result = await invocation(arguments)
                if isinstance(result, InputRequiredToolResult):
                    return result
                if not result.is_error:
                    progress.completed()
                if isinstance(result, BuiltinToolResult):
                    return result
                return self.prepare(result, arguments)
            except (asyncio.CancelledError, AuthorizationError, MCPError):
                raise
            except Exception as error:
                details, retry, notices = self._failure(error, progress.state)
                state = progress.state
                if not isinstance(error, (BuiltinToolArgumentError, BuiltinToolAuthorizationDenied, BuiltinToolError, ModelValidationError, ValidationError, ToolAuthorizationDenied)):
                    if state == OperationState.NOT_STARTED:
                        state = OperationState.UNKNOWN
                if state != OperationState.NOT_STARTED and retry not in {RetryAdvice.NEVER, RetryAdvice.INSPECT_BEFORE_RETRY}:
                    retry = RetryAdvice.INSPECT_BEFORE_RETRY
                metadata = self._factory.failure(
                    request_id, error=details, operation_state=state, retry=retry, notices=notices,
                    instructions=recovery_instructions(self._tool.name, arguments, details.code, state),
                )
                return self._failure_result(metadata)

    def prepare(self, result: ToolResult, arguments: dict[str, Any]) -> ToolResult:
        if isinstance(result, InputRequiredToolResult):
            return result
        try:
            return self._adapt_result(
                result, arguments, current_request_id() or uuid4().hex, operation_state(),
            )
        except (AuthorizationError, MCPError):
            raise
        except Exception:
            raise ToolResponseContractError() from None

    def _adapt_result(
        self, result: ToolResult, arguments: dict[str, Any], request_id: str, state: OperationState,
    ) -> BuiltinToolResult:
        if result.is_error:
            details = ToolErrorDetails(
                code="tool_returned_failure", message="The tool reported a failure. Inspect its state before retrying.", issues=(),
            )
            state = state if state != OperationState.NOT_STARTED else OperationState.UNKNOWN
            metadata = self._factory.failure(
                request_id, error=details, operation_state=state, retry=RetryAdvice.INSPECT_BEFORE_RETRY, notices=(),
                instructions=recovery_instructions(self._tool.name, arguments, details.code, state),
            )
        else:
            metadata = self._factory.success(request_id, notices=())
        return self._attach(result, metadata)

    def _failure_result(self, metadata: ToolFailureMetadata) -> BuiltinToolResult:
        return BuiltinToolResult(
            content=render_failure_guidance(metadata),
            is_error=True,
            meta={RESPONSE_METADATA_KEY: metadata.model_dump(mode="json")},
        )

    def completed(self) -> None:
        operation_completed()

    def _failure(self, error: Exception, state: OperationState) -> tuple[ToolErrorDetails, RetryAdvice, tuple[ToolNotice, ...]]:
        if isinstance(error, BuiltinToolArgumentError):
            return error.details, error.retry, error.notices
        if isinstance(error, (BuiltinToolAuthorizationDenied, BuiltinToolError)):
            return error.details, error.retry, ()
        if isinstance(error, ToolResponseContractError):
            return ToolErrorDetails(
                code="tool_response_contract_invalid", message="The response did not match the tool output schema.", issues=(),
            ), RetryAdvice.INSPECT_BEFORE_RETRY, ()
        if state == OperationState.NOT_STARTED:
            if isinstance(error, ModelValidationError):
                return self._argument_failure(error)
            if isinstance(error, ValidationError):
                if isinstance(error.__cause__, ModelValidationError):
                    return self._argument_failure(error.__cause__)
                details = ToolErrorDetails(code="invalid_arguments", message="Invalid tool arguments. Use arguments matching the tool input schema.", issues=())
                return details, RetryAdvice.AFTER_CORRECTION, ()
            if isinstance(error, ToolAuthorizationDenied):
                details = ToolErrorDetails(code="tool_permission_denied", message="Tool access denied. Request the required permissions.", issues=())
                return details, RetryAdvice.AFTER_PERMISSION_CHANGE, ()
        details = ToolErrorDetails(
            code="tool_operation_failed", message="The tool operation failed. Inspect its state before retrying and contact an administrator with the request ID if needed.", issues=(),
        )
        return details, RetryAdvice.INSPECT_BEFORE_RETRY, ()

    def _argument_failure(self, error: ModelValidationError) -> tuple[ToolErrorDetails, RetryAdvice, tuple[ToolNotice, ...]]:
        diagnostics = argument_diagnostics(self._tool, error, generic_correction)
        details = ToolErrorDetails(code="invalid_arguments", message="Invalid tool arguments.", issues=diagnostics.issues)
        return details, RetryAdvice.AFTER_CORRECTION, argument_notices(diagnostics.truncated)

    def _attach(self, result: ToolResult, metadata: ToolResponseMetadata) -> BuiltinToolResult:
        wire = result.to_mcp_result()
        if not isinstance(wire, CallToolResult):
            wire = CallToolResult(
                content=result.content, structured_content=result.structured_content,
                is_error=result.is_error, _meta=result.meta,
            )
        content = list(wire.content)
        if not wire.is_error and wire.structured_content is not None:
            content.extend(serialized_payload_content(content, wire.structured_content))
        content.extend(render_response_guidance(metadata))
        response = wire.model_copy(update={
            "content": content,
            "meta": {**(wire.meta or {}), RESPONSE_METADATA_KEY: metadata.model_dump(mode="json")},
        })
        return BuiltinToolResult.from_mcp_result(response)
