from functools import partial
from typing import Any

from fastmcp.server.dependencies import get_context
from fastmcp.server.providers.proxy import ProxyTool
from fastmcp.tools import ToolResult
from jsonschema.validators import validator_for

from umbod.core.capabilities import CapabilityIdentity
from umbod.core.invocation import (
    ConnectorInvocationDenied,
    ConnectorInvocationPolicy,
)
from umbod.core.invocation.tools.execution import PreparedToolExecution, ToolExecutionRequest, create_tool_execution_pipeline, prepare_tool_execution
from umbod.mcp.connectors import ModernConnectorApprovalRequired
from umbod.mcp.connectors.tools import (
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


class AuthorizedDownstreamProxyTool(ProxyTool):
    def __init__(
        self,
        *,
        identity: ConnectorToolInvocationIdentity,
        backend_tool: ProxyTool,
        client_factory: object,
        public_name: str,
        invocation_policy: ConnectorInvocationPolicy,
        telemetry_interceptor: ConnectorTelemetryInterceptor,
    ) -> None:
        super().__init__(**_proxy_tool_options(backend_tool, client_factory, public_name))
        self._backend_name = backend_tool.name
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
        try:
            return await self._execution_pipeline.execute(
                request,
                partial(self._prepare_execution, arguments),
            )
        except ModernConnectorApprovalRequired:
            raise
        except ConnectorInvocationDenied as error:
            raise RuntimeError("Connector invocation denied") from error

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
        context = get_context()
        try:
            result = await super().run(
                arguments,
                context=_InitialDownstreamContext(context),
            )
        except Exception:
            return _safe_downstream_failure()
        return _safe_downstream_failure() if result.is_error else result


def _safe_downstream_failure() -> ToolResult:
    return ToolResult(content="Tool invocation failed", is_error=True)


def _proxy_tool_options(
    backend_tool: ProxyTool, client_factory: object, public_name: str
) -> dict[str, Any]:
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
    return {"client_factory": client_factory, "name": public_name, **options}
