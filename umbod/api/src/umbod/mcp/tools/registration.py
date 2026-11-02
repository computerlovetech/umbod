import asyncio
import json

from collections.abc import Callable
from functools import lru_cache
from typing import Any, TypedDict, Unpack

from fastmcp import FastMCP
from fastmcp.exceptions import AuthorizationError, ValidationError
from fastmcp.tools import FunctionTool, InputRequiredToolResult, ToolResult
from fastmcp.tools.base import Tool
from mcp.shared.exceptions import MCPError
from pydantic import PrivateAttr
from jsonschema.exceptions import SchemaError
from jsonschema.exceptions import ValidationError as JsonSchemaValidationError
from jsonschema.protocols import Validator
from jsonschema.validators import validator_for
from referencing import Registry
from referencing.exceptions import Unresolvable

from umbod.build_identity import UMBOD_RELEASE, UMBOD_REVISION
from umbod.core.responses import ToolResponseMetadataFactory
from umbod.mcp.responses.ports import ToolResponseAdapter
from umbod.core.invocation.diagnostics import InvocationFailureDiagnostic

from umbod.core.invocation.failure_evidence import (
    InvocationFailureEvidence,
    InvocationFailureOrigin,
    InvocationReturnedFailure,
    exception_evidence,
)
from umbod.mcp.tools.errors import ToolAuthorizationDenied, ToolResponseContractError
from umbod.mcp.signals import McpInvocationPublisher
from umbod.mcp.signals.lifecycle import UnavailableToolInvocationLifecycle
from umbod.mcp.signals.events import McpToolIdentity, McpToolInvocationFailureCategory


@lru_cache(maxsize=128)
def _response_validator(serialized_schema: str) -> Validator:
    schema = json.loads(serialized_schema)
    validator_type = validator_for(schema)
    validator_type.check_schema(schema)
    return validator_type(schema, registry=Registry())


def tool_result_is_error(result: ToolResult) -> bool:
    return result.is_error


class ToolResponseOptions(TypedDict, total=False):
    builtin_response: bool


class ObservedToolOptions(ToolResponseOptions, total=False):
    tags: set[str]
    meta: dict[str, Any]
    result_is_error: Callable[[ToolResult], bool]


class ObservedFunctionTool(Tool):
    _delegate: Tool = PrivateAttr()
    _publisher: McpInvocationPublisher = PrivateAttr()
    _result_is_error: Callable[[ToolResult], bool] = PrivateAttr()
    _operation_names: frozenset[str] = PrivateAttr()
    _response_adapter: ToolResponseAdapter = PrivateAttr()

    def __init__(
        self, delegate: Tool, publisher: McpInvocationPublisher,
        result_is_error: Callable[[ToolResult], bool],
        operation_names: frozenset[str], response_adapter: ToolResponseAdapter,
    ) -> None:
        super().__init__(**{field: getattr(delegate, field) for field in Tool.model_fields})
        self._delegate = delegate
        self._publisher = publisher
        self._result_is_error = result_is_error
        self._operation_names = operation_names
        self._response_adapter = response_adapter

    async def run(self, arguments: dict[str, Any]) -> ToolResult:
        return await self._response_adapter.invoke(self._run_observed, arguments)

    async def _run_observed(self, arguments: dict[str, Any]) -> ToolResult:
        operation = arguments.get("operation")
        operation_name = operation if isinstance(operation, str) and operation in self._operation_names else None
        try:
            lifecycle = self._publisher.start(McpToolIdentity(tool_name=self.name, connector_id=None, operation_name=operation_name))
        except Exception as error:
            self._publisher.report_failure("invocation.start", error)
            lifecycle = UnavailableToolInvocationLifecycle()
        try:
            result = await self._delegate.run(arguments)
        except (asyncio.CancelledError, AuthorizationError, MCPError):
            raise
        except ToolAuthorizationDenied as error:
            self._publish_failure(lifecycle, McpToolInvocationFailureCategory.AUTHORIZATION, exception_evidence(error, InvocationFailureOrigin.INTERNAL))
            raise
        except ValidationError as error:
            self._publish_failure(lifecycle, McpToolInvocationFailureCategory.VALIDATION, exception_evidence(error, InvocationFailureOrigin.INTERNAL))
            raise
        except Exception as error:
            self._publish_failure(lifecycle, McpToolInvocationFailureCategory.UNEXPECTED_ERROR, exception_evidence(error, InvocationFailureOrigin.INTERNAL))
            raise
        if isinstance(result, InputRequiredToolResult):
            return result
        try:
            is_error = self._result_is_error(result)
        except Exception as error:
            self._publisher.report_failure("invocation.result_classification", error)
            self._publish_failure(lifecycle, McpToolInvocationFailureCategory.UNEXPECTED_ERROR, exception_evidence(error, InvocationFailureOrigin.INTERNAL))
            return result
        try:
            if not is_error:
                self._response_adapter.completed()
                self._validate_response(result)
            result = self._response_adapter.prepare(result, arguments)
        except ToolResponseContractError as error:
            self._publish_response_failure(lifecycle, error)
            raise
        if is_error:
            self._publish_failure(lifecycle, McpToolInvocationFailureCategory.UNEXPECTED_ERROR, InvocationReturnedFailure(InvocationFailureOrigin.INTERNAL))
        else:
            self._publish_success(lifecycle)
        return result

    def _validate_response(self, result: ToolResult) -> None:
        if self.output_schema is None:
            return
        if result.structured_content is None:
            raise ToolResponseContractError()
        try:
            serialized_schema = json.dumps(self.output_schema, sort_keys=True, separators=(",", ":"))
            _response_validator(serialized_schema).validate(result.structured_content)
        except (JsonSchemaValidationError, SchemaError, Unresolvable, TypeError, ValueError):
            pass
        else:
            return
        raise ToolResponseContractError()

    def _publish_success(self, lifecycle: Any) -> None:
        try:
            self._publisher.succeeded(lifecycle)
        except Exception as error:
            self._publisher.report_failure("invocation.success", error)

    def _publish_failure(
        self, lifecycle: Any, category: McpToolInvocationFailureCategory,
        evidence: InvocationFailureEvidence,
    ) -> None:
        try:
            self._publisher.failed(lifecycle, category, None, evidence)
        except Exception as error:
            self._publisher.report_failure("invocation.failure", error)

    def _publish_response_failure(self, lifecycle: Any, error: ToolResponseContractError) -> None:
        evidence = exception_evidence(error, InvocationFailureOrigin.INTERNAL)
        diagnostic = InvocationFailureDiagnostic(execution_mode="shared", stage="output", reason="invalid_output")
        try:
            self._publisher.failed(lifecycle, McpToolInvocationFailureCategory.UNEXPECTED_ERROR, diagnostic, evidence)
        except Exception as receiver_error:
            self._publisher.report_failure("invocation.failure", receiver_error)


class McpObservedToolRegistrar:
    def __init__(self, mcp: FastMCP, publisher: McpInvocationPublisher) -> None:
        self._mcp = mcp
        self._publisher = publisher
        self._response_factory = ToolResponseMetadataFactory(UMBOD_RELEASE, UMBOD_REVISION)

    def register(
        self,
        fn: Callable[..., Any],
        *,
        name: str,
        description: str,
        auth: Any,
        **options: Unpack[ObservedToolOptions],
    ) -> ObservedFunctionTool:
        delegate = FunctionTool.from_function(
            fn, name=name, description=description, auth=auth,
            tags=options.get("tags", set()), meta=options.get("meta", {}),
        )
        return self.register_tool(
            delegate, result_is_error=options.get("result_is_error", tool_result_is_error),
            operation_names=frozenset(), builtin_response=options.get("builtin_response", False),
        )

    def register_tool(
        self, delegate: Tool, *,
        result_is_error: Callable[[ToolResult], bool],
        operation_names: frozenset[str], **options: Unpack[ToolResponseOptions],
    ) -> ObservedFunctionTool:
        from umbod.mcp.responses.adapter import BuiltinToolResponseAdapter, UnmodifiedToolResponseAdapter
        from umbod.mcp.responses.validation import BuiltinArgumentErrorsTool

        builtin_response = options.get("builtin_response", False)
        response_adapter = BuiltinToolResponseAdapter(self._response_factory, delegate) if builtin_response else UnmodifiedToolResponseAdapter()
        observed_delegate = BuiltinArgumentErrorsTool(delegate) if builtin_response else delegate
        tool = ObservedFunctionTool(observed_delegate, self._publisher, result_is_error, operation_names, response_adapter)
        self._mcp.add_tool(tool)
        self._publisher.tool_registered(McpToolIdentity(tool_name=delegate.name, connector_id=None, operation_name=None))
        return tool
