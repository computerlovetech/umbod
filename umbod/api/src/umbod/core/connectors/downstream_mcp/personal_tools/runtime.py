from collections.abc import Callable
from datetime import datetime

from jsonschema.exceptions import ValidationError

from umbod.core.invocation.failure_evidence import (
    InvocationFailureOrigin,
    capture_invocation_exception,
    capture_returned_failure,
    current_invocation_failure,
)

from umbod.core.invocation.diagnostics import InvocationFailureDiagnostic, PERSONAL_RUNTIME_FAILURE

from ..models import DiscoveredTool, uses_personal_oauth
from ..personal_connections.health_models import RejectPersonalAuthorization, PersonalAuthorizationHealthUnavailable
from ..personal_connections.runtime_models import PersonalAuthorizationRejected
from ..personal_connections.models import PersonalConnectionKey
from ..personal_connections.runtime_models import PersonalRuntimeAuthorizationQuery, PersonalRuntimeUnavailable, PersonalToolCall, PersonalToolResult
from ..personal_connections.runtime_ports import PersonalMcpTransport
from ..stores.ports import ConnectorDefinitionStore
from .contract_validation import validate_arguments, validate_output
from .models import AdmitPersonalTool, InvokePersonalTool, PersonalToolRecord
from .ports import PersonalToolAccessStore
from ..personal_connections.caller import PersonalCaller, UnavailablePersonalCaller, require_personal_caller
from ..personal_connections.models import MissingCanonicalPrincipal
from .schema_validation import PersonalToolPolicyInvalid


_INVALID_OUTPUT = InvocationFailureDiagnostic(execution_mode="personal", stage="output", reason="invalid_output")


def _validate_result(tool: DiscoveredTool, result: PersonalToolResult) -> None:
    if result.result.get("isError", False) is True:
        capture_returned_failure(InvocationFailureOrigin.MCP)
        raise PersonalRuntimeUnavailable("Personal tool unavailable", diagnostic=InvocationFailureDiagnostic(execution_mode="personal", stage="downstream", reason="downstream_tool_error"))
    if not isinstance(result.result.get("content"), list) or result.result.get("isError", False) is not False:
        raise PersonalRuntimeUnavailable("Personal tool unavailable", diagnostic=_INVALID_OUTPUT)
    if "structuredContent" in result.result:
        output = result.result["structuredContent"]
        if not isinstance(output, dict):
            raise PersonalRuntimeUnavailable("Personal tool unavailable", diagnostic=_INVALID_OUTPUT)
        validate_output(tool, output)
    elif tool.output_schema_status == "present":
        raise PersonalRuntimeUnavailable("Personal tool unavailable", diagnostic=_INVALID_OUTPUT)


class DisabledPersonalToolRuntime:
    async def list_tools(self) -> tuple[PersonalToolRecord, ...]:
        return ()

    async def execute(self, command: InvokePersonalTool) -> PersonalToolResult:
        raise PersonalRuntimeUnavailable("Personal tool unavailable")


class PersonalToolRuntimeService:
    def __init__(
        self,
        caller: PersonalCaller | UnavailablePersonalCaller,
        definitions: ConnectorDefinitionStore,
        access: PersonalToolAccessStore,
        transport: PersonalMcpTransport,
        clock: Callable[[], datetime],
    ) -> None:
        self._caller = caller
        self._definitions = definitions
        self._access = access
        self._transport = transport
        self._clock = clock

    def _capture(self) -> PersonalCaller:
        try:
            return require_personal_caller(self._caller)
        except MissingCanonicalPrincipal as error:
            if current_invocation_failure() is None:
                capture_invocation_exception(error, InvocationFailureOrigin.INTERNAL)
            raise PersonalRuntimeUnavailable("Personal identity unavailable") from None

    async def list_tools(self) -> tuple[PersonalToolRecord, ...]:
        try:
            context = self._capture()
        except PersonalRuntimeUnavailable:
            return ()
        records: list[PersonalToolRecord] = []
        for definition in (await self._definitions.list()).definitions:
            if not uses_personal_oauth(definition):
                continue
            records.extend(await self._access.list_available(PersonalRuntimeAuthorizationQuery(
                key=PersonalConnectionKey(principal=context.principal, connector_id=definition.connector_id),
                group_ids=context.groups.group_ids,
                now=self._clock(),
            )))
        return tuple(records)

    async def execute(self, command: InvokePersonalTool) -> PersonalToolResult:
        stage = "context"
        try:
            context = self._capture()
            stage = "admission"
            admission = await self._access.admit(AdmitPersonalTool(
                query=PersonalRuntimeAuthorizationQuery(
                    key=PersonalConnectionKey(principal=context.principal, connector_id=command.identity.connector_id),
                    group_ids=context.groups.group_ids,
                    now=self._clock(),
                ),
                identity=command.identity,
                inventory_revision=command.inventory_revision,
                fingerprint=command.fingerprint,
            ))
            stage = "arguments"
            validate_arguments(admission.tool, command.arguments)
            stage = "transport"
            try:
                result = await self._transport.call_tool(PersonalToolCall(
                    target=admission.target,
                    tool_name=command.identity.capability_key,
                    expected_fingerprint=command.fingerprint,
                    arguments=command.arguments,
                ))
            except PersonalAuthorizationRejected as error:
                if current_invocation_failure() is None:
                    capture_invocation_exception(error, InvocationFailureOrigin.MCP)
                await self._access.reject_authorization(RejectPersonalAuthorization(
                    key=admission.target.key,
                    expected_connection_revision=admission.target.authorization_revision,
                ))
                raise PersonalRuntimeUnavailable("Personal tool unavailable", diagnostic=InvocationFailureDiagnostic(execution_mode="personal", stage="authorization", reason="authorization_rejected")) from None
            stage = "output"
            _validate_result(admission.tool, result)
            return result
        except PersonalAuthorizationHealthUnavailable as error:
            capture_invocation_exception(error, InvocationFailureOrigin.INTERNAL)
            raise
        except PersonalRuntimeUnavailable as error:
            if current_invocation_failure() is None:
                capture_invocation_exception(error, InvocationFailureOrigin.MCP if stage == "transport" else InvocationFailureOrigin.INTERNAL)
            diagnostic = error.diagnostic
            if diagnostic == PERSONAL_RUNTIME_FAILURE:
                diagnostic = {
                    "context": InvocationFailureDiagnostic(execution_mode="personal", stage="context", reason="context_unavailable"),
                    "admission": InvocationFailureDiagnostic(execution_mode="personal", stage="admission", reason="admission_denied"),
                    "transport": InvocationFailureDiagnostic(execution_mode="personal", stage="transport", reason="transport_failure"),
                }.get(stage, PERSONAL_RUNTIME_FAILURE)
        except (ValidationError, PersonalToolPolicyInvalid) as error:
            if current_invocation_failure() is None:
                capture_invocation_exception(error, InvocationFailureOrigin.INTERNAL)
            diagnostic = {
                "arguments": InvocationFailureDiagnostic(execution_mode="personal", stage="arguments", reason="invalid_arguments"),
                "output": _INVALID_OUTPUT,
            }.get(stage, PERSONAL_RUNTIME_FAILURE)
        except Exception as error:
            if current_invocation_failure() is None:
                capture_invocation_exception(error, InvocationFailureOrigin.INTERNAL)
            diagnostic = PERSONAL_RUNTIME_FAILURE
        raise PersonalRuntimeUnavailable("Personal tool unavailable", diagnostic=diagnostic)
