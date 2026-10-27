from functools import partial
from collections.abc import Awaitable, Callable

import anyio
import httpx2
from fastmcp.exceptions import ClientError, ToolError
from mcp.shared.exceptions import MCPError

from umbod.core.invocation.failure_evidence import (
    InvocationFailureOrigin,
    capture_invocation_exception,
    capture_returned_failure,
    current_invocation_failure,
)

from umbod.core.invocation.diagnostics import InvocationFailureDiagnostic
from umbod.core.connectors.downstream_mcp.personal_connections.runtime_models import PersonalRuntimeUnavailable
from umbod.core.connectors.downstream_mcp.personal_connections.health_models import PersonalAuthorizationHealthUnavailable
from umbod.mcp.signals.diagnostics import invocation_failure
from typing import Any

from fastmcp.server.dependencies import get_context
from fastmcp.server.providers.proxy import ProxyTool
from fastmcp.tools import ToolResult
from fastmcp.tools.base import Tool
from mcp.types import CallToolResult
from umbod.core.connectors.downstream_mcp.personal_tools import InvokePersonalTool, PersonalToolRecord, PersonalToolRuntime
from jsonschema.validators import validator_for
from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError
from umbod.core.connectors.downstream_mcp.personal_tools.schema_validation import PersonalToolPolicyInvalid
from referencing import Registry
from umbod.core.connectors.downstream_mcp.personal_tools import validate_contract_schema

from umbod.core.capabilities import CapabilityIdentity
from umbod.core.invocation import (
    ConnectorInvocationDenied,
)
from umbod.core.invocation.tools.execution import PreparedToolExecution, ToolExecutionRequest, ToolExecutionPipeline, prepare_tool_execution
from umbod.mcp.connectors.native import ModernConnectorApprovalRequired
from umbod.mcp.signals import McpToolIdentity


class _InitialDownstreamContext:
    def __init__(self, context: Any) -> None:
        self._context = context

    @property
    def request_state(self) -> None:
        return None

    @property
    def input_responses(self) -> None:
        return None

    def __getattr__(self, name: str) -> Any:
        return getattr(self._context, name)


class AuthorizedDownstreamTool(Tool):
    def __init__(
        self,
        *,
        identity: McpToolIdentity,
        options: dict[str, Any],
        public_name: str,
        execution_pipeline: ToolExecutionPipeline[ToolResult],
    ) -> None:
        super().__init__(name=public_name, **options)
        self._identity = identity
        self._execution_pipeline = execution_pipeline

    async def run(self, arguments: dict[str, Any]) -> ToolResult:
        try:
            return await self._execute(arguments)
        except ModernConnectorApprovalRequired as approval:
            return approval.result

    async def _execute(self, arguments: dict[str, Any]) -> ToolResult:
        request = self._execution_request(arguments)
        diagnostic_token = invocation_failure.set(None)
        try:
            return await self._execution_pipeline.execute(
                request,
                partial(self._prepare_execution, arguments),
            )
        except ModernConnectorApprovalRequired:
            raise
        except ConnectorInvocationDenied as error:
            raise RuntimeError("Connector invocation denied") from error
        finally:
            invocation_failure.reset(diagnostic_token)

    def _execution_request(self, arguments: dict[str, Any]) -> ToolExecutionRequest:
        return ToolExecutionRequest(
            identity=CapabilityIdentity(
                connector_kind="downstream_mcp",
                connector_id=self._identity.connector_id,
                capability_kind="tool",
            capability_key=self._identity.operation_name,
            ),
            public_tool_name=self._identity.tool_name,
            arguments=arguments,
        )

    async def _prepare_execution(
        self,
        arguments: dict[str, Any],
    ) -> PreparedToolExecution[ToolResult]:
        self._validate_arguments(arguments)
        return prepare_tool_execution(
            arguments,
            partial(self._invoke_downstream, arguments),
            arguments,
        )

    def _validate_arguments(self, arguments: dict[str, Any]) -> None:
        validator = validator_for(self.parameters)
        validator.check_schema(self.parameters)
        validator(self.parameters).validate(arguments)

    async def _invoke_downstream(self, arguments: dict[str, Any]) -> ToolResult:
        raise NotImplementedError


class AuthorizedDownstreamProxyTool(AuthorizedDownstreamTool):
    def __init__(self, *, identity: McpToolIdentity, backend_tool: ProxyTool, ensure_access: Callable[[], Awaitable[None]], public_name: str, execution_pipeline: ToolExecutionPipeline[ToolResult]) -> None:
        options = _proxy_tool_options(backend_tool)
        super().__init__(identity=identity, options=options, public_name=public_name, execution_pipeline=execution_pipeline)
        self._backend_tool = backend_tool
        self._ensure_access = ensure_access

    async def _invoke_downstream(self, arguments: dict[str, Any]) -> ToolResult:
        await self._ensure_access()
        context = get_context()
        try:
            result = await self._backend_tool.run(
                arguments,
                context=_InitialDownstreamContext(context),
            )
        except Exception as error:
            if current_invocation_failure() is None:
                capture_invocation_exception(error, _shared_failure_origin(error))
            invocation_failure.set(InvocationFailureDiagnostic(execution_mode="shared", stage="downstream", reason="downstream_exception"))
            return _safe_downstream_failure()
        if result.is_error:
            capture_returned_failure(InvocationFailureOrigin.MCP)
            invocation_failure.set(InvocationFailureDiagnostic(execution_mode="shared", stage="downstream", reason="downstream_tool_error"))
            return _safe_downstream_failure()
        return result


def _shared_failure_origin(error: BaseException) -> InvocationFailureOrigin:
    if isinstance(error, BaseExceptionGroup):
        return InvocationFailureOrigin.MCP if all(_shared_failure_origin(nested) == InvocationFailureOrigin.MCP for nested in error.exceptions) else InvocationFailureOrigin.INTERNAL
    if isinstance(error, (MCPError, ClientError, ToolError, httpx2.HTTPError, TimeoutError, anyio.EndOfStream, anyio.BrokenResourceError, anyio.ClosedResourceError)):
        return InvocationFailureOrigin.MCP
    return InvocationFailureOrigin.INTERNAL


def _safe_downstream_failure() -> ToolResult:
    return ToolResult(content="Tool invocation failed", is_error=True)


class AuthorizedPersonalTool(AuthorizedDownstreamTool):
    def __init__(self, *, identity: McpToolIdentity, record: PersonalToolRecord, runtime: PersonalToolRuntime, public_name: str, execution_pipeline: ToolExecutionPipeline[ToolResult], options: dict[str, Any]) -> None:
        super().__init__(identity=identity, options=options, public_name=public_name, execution_pipeline=execution_pipeline)
        self._runtime = runtime
        self._command = InvokePersonalTool(identity=CapabilityIdentity(connector_kind="downstream_mcp", connector_id=record.definition.connector_id, capability_kind="tool", capability_key=record.tool.identity.downstream_name), inventory_revision=record.inventory_revision, fingerprint=record.fingerprint, arguments={})

    def _validate_arguments(self, arguments: dict[str, Any]) -> None:
        try:
            validate_contract_schema(self.parameters)
            Draft202012Validator(self.parameters, registry=Registry()).validate(arguments)
            return
        except (ValidationError, PersonalToolPolicyInvalid) as error:
            capture_invocation_exception(error, InvocationFailureOrigin.INTERNAL)
            invocation_failure.set(InvocationFailureDiagnostic(execution_mode="personal", stage="arguments", reason="invalid_arguments"))
        except Exception as error:
            capture_invocation_exception(error, InvocationFailureOrigin.INTERNAL)
            invocation_failure.set(InvocationFailureDiagnostic(execution_mode="personal", stage="runtime", reason="runtime_failure"))
        raise RuntimeError("Personal tool unavailable")

    async def is_authorized(self) -> bool:
        return any(record.definition.connector_id == self._command.identity.connector_id and record.tool.identity.downstream_name == self._command.identity.capability_key and record.inventory_revision == self._command.inventory_revision and record.fingerprint == self._command.fingerprint for record in await self._runtime.list_tools())

    async def _invoke_downstream(self, arguments: dict[str, Any]) -> ToolResult:
        try:
            result = await self._runtime.execute(self._command.model_copy(update={"arguments": arguments}))
            downstream = CallToolResult(
                content=result.result["content"],
                structuredContent=result.result.get("structuredContent"),
                _meta=result.result.get("_meta"),
            )
            return ToolResult(
                content=downstream.content,
                structured_content=downstream.structured_content,
                meta=downstream.meta,
            )
        except PersonalAuthorizationHealthUnavailable as error:
            if current_invocation_failure() is None:
                capture_invocation_exception(error, InvocationFailureOrigin.INTERNAL)
            invocation_failure.set(InvocationFailureDiagnostic(execution_mode="personal", stage="authorization", reason="authorization_health_unavailable"))
        except PersonalRuntimeUnavailable as error:
            if current_invocation_failure() is None:
                capture_invocation_exception(error, InvocationFailureOrigin.INTERNAL)
            invocation_failure.set(error.diagnostic)
        except Exception as error:
            if current_invocation_failure() is None:
                capture_invocation_exception(error, InvocationFailureOrigin.INTERNAL)
            invocation_failure.set(InvocationFailureDiagnostic(execution_mode="personal", stage="runtime", reason="runtime_failure"))
        return _safe_downstream_failure()


def _proxy_tool_options(backend_tool: Tool) -> dict[str, Any]:
    field_names = (
        "version",
        "title",
        "description",
        "icons",
        "tags",
        "meta",
        "task_config",
        "parameters",
        "output_schema",
        "annotations",
        "execution",
        "auth",
        "timeout",
    )
    options = {name: getattr(backend_tool, name) for name in field_names}
    return options
