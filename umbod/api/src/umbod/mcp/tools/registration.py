import json

from collections.abc import Callable
from functools import lru_cache
from typing import Any, TypedDict, Unpack

from fastmcp import FastMCP
from fastmcp.tools import FunctionTool, InputRequiredToolResult, ToolResult
from fastmcp.tools.base import Tool
from pydantic import PrivateAttr
from jsonschema.exceptions import SchemaError
from jsonschema.exceptions import ValidationError as JsonSchemaValidationError
from jsonschema.protocols import Validator
from jsonschema.validators import validator_for
from referencing import Registry
from referencing.exceptions import Unresolvable

from umbod.build_identity import UMBOD_RELEASE, UMBOD_REVISION
from umbod.core.invocation.diagnostics import NoInvocationFailureDiagnostic
from umbod.core.invocation.failure_evidence import (
    InvocationExceptionEvidence,
    InvocationFailureOrigin,
    InvocationReturnedFailure,
    current_invocation_failure,
)
from umbod.core.invocation.tools.ordered_execution import OrderedExecutionRunner, PreparedExecution
from umbod.core.responses import ToolResponseMetadataFactory
from umbod.core.usage.models import BuiltinUsageToolTarget
from umbod.mcp.responses.ports import ToolResponseAdapter
from umbod.mcp.signals import McpInvocationPublisher, McpInvocationPublishing
from umbod.mcp.signals.events import McpToolIdentity, McpToolInvocationFailureCategory
from umbod.mcp.signals.publisher import IsolatedInvocationPublishing
from umbod.mcp.tools.errors import ToolResponseContractError
from umbod.mcp.tools.observation import (
    ObservedToolFailure, ObservedToolResponse, ObservedToolSignalInterceptor, classify_raised_failure,
)


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
    _publisher: IsolatedInvocationPublishing = PrivateAttr()
    _runner: OrderedExecutionRunner[McpToolIdentity, None, ObservedToolResponse] = PrivateAttr()
    _result_is_error: Callable[[ToolResult], bool] = PrivateAttr()
    _operation_names: frozenset[str] = PrivateAttr()
    _response_adapter: ToolResponseAdapter = PrivateAttr()

    def __init__(
        self, delegate: Tool, publisher: McpInvocationPublishing,
        result_is_error: Callable[[ToolResult], bool],
        operation_names: frozenset[str], response_adapter: ToolResponseAdapter,
    ) -> None:
        super().__init__(**{field: getattr(delegate, field) for field in Tool.model_fields})
        self._delegate = delegate
        self._publisher = IsolatedInvocationPublishing(publisher)
        self._runner = OrderedExecutionRunner((ObservedToolSignalInterceptor(self._publisher),))
        self._result_is_error = result_is_error
        self._operation_names = operation_names
        self._response_adapter = response_adapter

    async def run(self, arguments: dict[str, Any]) -> ToolResult:
        with self._response_adapter.invocation_context():
            return await self._run_observed(arguments)

    async def _run_observed(self, arguments: dict[str, Any]) -> ToolResult:
        operation = arguments.get("operation")
        operation_name = operation if isinstance(operation, str) and operation in self._operation_names else None
        identity = McpToolIdentity(
            tool_name=self.name, connector_id=None, operation_name=operation_name,
            usage_target=BuiltinUsageToolTarget(kind="builtin", registered_name=self._delegate.name),
        )

        async def prepare() -> PreparedExecution[None, ObservedToolResponse]:
            async def execute() -> ObservedToolResponse:
                return await self._prepare_observed_response(arguments)

            return PreparedExecution(context=None, operation=execute)

        response = await self._runner.execute(identity, prepare)
        return response.result

    async def _prepare_observed_response(self, arguments: dict[str, Any]) -> ObservedToolResponse:
        try:
            return await self._execute(arguments)
        except Exception as error:
            failure = classify_raised_failure(error)
            if failure is None:
                raise
            response = self._response_adapter.prepare_failure(error, arguments)
            if response is None:
                raise
            return ObservedToolResponse(response, failure)

    async def _execute(self, arguments: dict[str, Any]) -> ObservedToolResponse:
        result = await self._delegate.run(arguments)
        if isinstance(result, InputRequiredToolResult):
            return ObservedToolResponse(result, None)
        try:
            is_error = self._result_is_error(result)
        except Exception as error:
            failure = ObservedToolFailure.unexpected(error)
            self._publisher.report_failure("invocation.result_classification", error)
            if not result.is_error:
                self._response_adapter.completed()
            return ObservedToolResponse(self._response_adapter.prepare(result, arguments), failure)
        if not is_error:
            self._response_adapter.completed()
            self._validate_response(result)
        result = self._response_adapter.prepare(result, arguments)
        if not is_error:
            return ObservedToolResponse(result, None)
        evidence = current_invocation_failure() or InvocationReturnedFailure(InvocationFailureOrigin.INTERNAL)
        category = (
            McpToolInvocationFailureCategory.UNEXPECTED_ERROR
            if isinstance(evidence, InvocationExceptionEvidence)
            else McpToolInvocationFailureCategory.TOOL_ERROR
        )
        return ObservedToolResponse(result, ObservedToolFailure(category, evidence, NoInvocationFailureDiagnostic()))

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
        self._publisher.tool_registered(McpToolIdentity(tool_name=delegate.name, connector_id=None, operation_name=None, usage_target=BuiltinUsageToolTarget(kind='builtin', registered_name=delegate.name)))
        return tool
