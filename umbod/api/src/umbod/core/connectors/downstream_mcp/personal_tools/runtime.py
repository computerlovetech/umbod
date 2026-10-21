from collections.abc import Callable
from datetime import datetime

from ..models import DiscoveredTool, uses_personal_oauth
from ..personal_connections.models import PersonalConnectionKey
from ..personal_connections.runtime_models import PersonalRuntimeAuthorizationQuery, PersonalRuntimeUnavailable, PersonalToolCall, PersonalToolResult
from ..personal_connections.runtime_ports import PersonalMcpTransport
from ..stores.ports import ConnectorDefinitionStore
from .contract_validation import validate_arguments, validate_output
from .models import AdmitPersonalTool, InvokePersonalTool, PersonalToolRecord
from .ports import PersonalRuntimeContextProvider, PersonalToolAccessStore


def _validate_result(tool: DiscoveredTool, result: PersonalToolResult) -> None:
    if not isinstance(result.result.get("content"), list) or result.result.get("isError", False) is not False:
        raise PersonalRuntimeUnavailable("Personal tool unavailable")
    if "structuredContent" in result.result:
        output = result.result["structuredContent"]
        if not isinstance(output, dict):
            raise PersonalRuntimeUnavailable("Personal tool unavailable")
        validate_output(tool, output)
    elif tool.output_schema_status == "present":
        raise PersonalRuntimeUnavailable("Personal tool unavailable")


class DisabledPersonalToolRuntime:
    async def list_tools(self) -> tuple[PersonalToolRecord, ...]:
        return ()

    async def execute(self, command: InvokePersonalTool) -> PersonalToolResult:
        raise PersonalRuntimeUnavailable("Personal tool unavailable")


class PersonalToolRuntimeService:
    def __init__(
        self,
        contexts: PersonalRuntimeContextProvider,
        definitions: ConnectorDefinitionStore,
        access: PersonalToolAccessStore,
        transport: PersonalMcpTransport,
        clock: Callable[[], datetime],
    ) -> None:
        self._contexts = contexts
        self._definitions = definitions
        self._access = access
        self._transport = transport
        self._clock = clock

    async def list_tools(self) -> tuple[PersonalToolRecord, ...]:
        try:
            context = await self._contexts.get_context()
        except PersonalRuntimeUnavailable:
            return ()
        records: list[PersonalToolRecord] = []
        for definition in (await self._definitions.list()).definitions:
            if not uses_personal_oauth(definition):
                continue
            records.extend(await self._access.list_available(PersonalRuntimeAuthorizationQuery(
                key=PersonalConnectionKey(principal=context.principal, connector_id=definition.connector_id),
                group_ids=context.group_ids,
                now=self._clock(),
            )))
        return tuple(records)

    async def execute(self, command: InvokePersonalTool) -> PersonalToolResult:
        try:
            context = await self._contexts.get_context()
            admission = await self._access.admit(AdmitPersonalTool(
                query=PersonalRuntimeAuthorizationQuery(
                    key=PersonalConnectionKey(principal=context.principal, connector_id=command.identity.connector_id),
                    group_ids=context.group_ids,
                    now=self._clock(),
                ),
                identity=command.identity,
                contract_revision=command.contract_revision,
                fingerprint=command.fingerprint,
            ))
            validate_arguments(admission.tool, command.arguments)
            result = await self._transport.call_tool(PersonalToolCall(
                target=admission.target,
                tool_name=command.identity.capability_key,
                expected_fingerprint=command.fingerprint,
                arguments=command.arguments,
            ))
            _validate_result(admission.tool, result)
            return result
        except Exception:
            pass
        raise PersonalRuntimeUnavailable("Personal tool unavailable")
