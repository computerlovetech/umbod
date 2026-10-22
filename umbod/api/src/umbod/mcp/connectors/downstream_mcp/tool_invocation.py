from functools import partial

from umbod.core.invocation.diagnostics import InvocationFailureDiagnostic
from umbod.core.connectors.downstream_mcp.personal_connections.runtime_models import PersonalRuntimeUnavailable
from umbod.core.connectors.downstream_mcp.personal_connections.health_models import PersonalAuthorizationHealthUnavailable
from umbod.mcp.tools.invocation.diagnostics import invocation_failure
from typing import Any

from fastmcp.server.dependencies import get_context
from fastmcp.server.providers.proxy import ProxyTool
from fastmcp.tools import ToolResult
from fastmcp.tools.base import Tool
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
    ConnectorInvocationPolicy,
)
from umbod.core.invocation.tools.execution import PreparedToolExecution, ToolExecutionRequest, create_tool_execution_pipeline, prepare_tool_execution
from umbod.mcp.connectors.native import ModernConnectorApprovalRequired
from umbod.mcp.connectors.native.tools import (
    ConnectorTelemetryInterceptor,
    ConnectorToolInvocationIdentity,
)


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
        identity: ConnectorToolInvocationIdentity,
        options: dict[str, Any],
        public_name: str,
        invocation_policy: ConnectorInvocationPolicy,
        telemetry_interceptor: ConnectorTelemetryInterceptor,
    ) -> None:
        super().__init__(name=public_name, **options)
        self._identity = identity
        self._execution_pipeline = create_tool_execution_pipeline(
            invocation_policy, (telemetry_interceptor,)
        )

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
    def __init__(self, *, identity: ConnectorToolInvocationIdentity, backend_tool: ProxyTool, client_factory: object, public_name: str, invocation_policy: ConnectorInvocationPolicy, telemetry_interceptor: ConnectorTelemetryInterceptor) -> None:
        options = _proxy_tool_options(backend_tool)
        super().__init__(identity=identity, options=options, public_name=public_name, invocation_policy=invocation_policy, telemetry_interceptor=telemetry_interceptor)
        self._backend_tool = backend_tool

    async def _invoke_downstream(self, arguments: dict[str, Any]) -> ToolResult:
        context = get_context()
        try:
            result = await self._backend_tool.run(
                arguments,
                context=_InitialDownstreamContext(context),
            )
        except Exception:
            invocation_failure.set(InvocationFailureDiagnostic(execution_mode="shared", stage="downstream", reason="downstream_exception"))
            return _safe_downstream_failure()
        if result.is_error:
            invocation_failure.set(InvocationFailureDiagnostic(execution_mode="shared", stage="downstream", reason="downstream_tool_error"))
            return _safe_downstream_failure()
        return result


def _safe_downstream_failure() -> ToolResult:
    return ToolResult(content="Tool invocation failed", is_error=True)


class AuthorizedPersonalTool(AuthorizedDownstreamTool):
    def __init__(self, *, identity: ConnectorToolInvocationIdentity, record: PersonalToolRecord, runtime: PersonalToolRuntime, public_name: str, invocation_policy: ConnectorInvocationPolicy, telemetry_interceptor: ConnectorTelemetryInterceptor, options: dict[str, Any]) -> None:
        super().__init__(identity=identity, options=options, public_name=public_name, invocation_policy=invocation_policy, telemetry_interceptor=telemetry_interceptor)
        self._runtime = runtime
        self._command = InvokePersonalTool(identity=CapabilityIdentity(connector_kind="downstream_mcp", connector_id=record.definition.connector_id, capability_kind="tool", capability_key=record.tool.identity.downstream_name), contract_revision=record.contract_revision, fingerprint=record.fingerprint, arguments={})

    def _validate_arguments(self, arguments: dict[str, Any]) -> None:
        try:
            validate_contract_schema(self.parameters)
            Draft202012Validator(self.parameters, registry=Registry()).validate(arguments)
            return
        except (ValidationError, PersonalToolPolicyInvalid):
            invocation_failure.set(InvocationFailureDiagnostic(execution_mode="personal", stage="arguments", reason="invalid_arguments"))
        except Exception:
            invocation_failure.set(InvocationFailureDiagnostic(execution_mode="personal", stage="runtime", reason="runtime_failure"))
        raise RuntimeError("Personal tool unavailable")

    async def is_authorized(self) -> bool:
        return any(record.definition.connector_id == self._command.identity.connector_id and record.tool.identity.downstream_name == self._command.identity.capability_key and record.contract_revision == self._command.contract_revision and record.fingerprint == self._command.fingerprint for record in await self._runtime.list_tools())

    async def _invoke_downstream(self, arguments: dict[str, Any]) -> ToolResult:
        try:
            result = await self._runtime.execute(self._command.model_copy(update={"arguments": arguments}))
            return ToolResult(**{"content": result.result["content"], **({"structured_content": result.result["structuredContent"]} if "structuredContent" in result.result else {})})
        except PersonalAuthorizationHealthUnavailable:
            invocation_failure.set(InvocationFailureDiagnostic(execution_mode="personal", stage="authorization", reason="authorization_health_unavailable"))
        except PersonalRuntimeUnavailable as error:
            invocation_failure.set(error.diagnostic)
        except Exception:
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
