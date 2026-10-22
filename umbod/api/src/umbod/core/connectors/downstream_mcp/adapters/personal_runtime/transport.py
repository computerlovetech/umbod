import ssl
from collections.abc import Callable
from datetime import datetime

import anyio
import httpcore2
import httpx2
from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport
from mcp import types
from pydantic import TypeAdapter

from umbod.core.invocation.diagnostics import InvocationFailureDiagnostic

from umbod.core.connectors.downstream_mcp.models import DiscoveredTool
from umbod.core.connectors.downstream_mcp.personal_connections.runtime_models import (
    PersonalAuthorizationRejected,
    PersonalRuntimeLimits,
    PersonalRuntimeTarget,
    PersonalRuntimeUnavailable,
    PersonalToolCall,
    PersonalToolInventory,
    PersonalToolResult,
)

from umbod.core.connectors.downstream_mcp.personal_tools.contract_validation import contract_fingerprint, validate_contract_schema

from .http import PersonalHttpTransport
from .network import PinnedPublicNetworkBackend, PublicAddressResolver
from .redaction import contains_secret
from .operation import OperationState
from .wire_models import StrictCallToolResult


class FastMCPPersonalMcpTransport:
    def __init__(
        self,
        limits: PersonalRuntimeLimits,
        clock: Callable[[], datetime],
        resolver: PublicAddressResolver,
        backend_factory: Callable[[], httpcore2.AsyncNetworkBackend],
        ssl_context: ssl.SSLContext,
    ) -> None:
        if not ssl_context.check_hostname or ssl_context.verify_mode != ssl.CERT_REQUIRED:
            raise ValueError("Personal MCP requires verified TLS")
        self._ssl_context = ssl_context
        self._limits = limits
        self._clock = clock
        self._resolver = resolver
        self._backend_factory = backend_factory

    async def list_tools(self, target: PersonalRuntimeTarget) -> PersonalToolInventory:
        result = await self._operate(target, target)
        return PersonalToolInventory.model_validate(result)

    async def call_tool(self, command: PersonalToolCall) -> PersonalToolResult:
        result = await self._operate(command.target, command)
        return PersonalToolResult.model_validate(result)

    async def _operate(
        self, target: PersonalRuntimeTarget, operation: PersonalRuntimeTarget | PersonalToolCall
    ) -> dict[str, object]:
        budget = min(self._limits.operation_timeout_seconds, (target.expires_at - self._clock()).total_seconds() - 0.1)
        if budget <= 0:
            raise PersonalRuntimeUnavailable("Personal MCP unavailable", diagnostic=InvocationFailureDiagnostic(execution_mode="personal", stage="transport", reason="target_expired"))
        scope = anyio.CancelScope(deadline=anyio.current_time() + budget)
        wire = OperationState(target, self._limits, self._clock, scope, operation)
        try:
            with scope:
                bridge = self._bridge(wire)
                client = self._client(bridge, target, budget)
                result = await self._session(client, bridge, wire)
                wire.check()
            if wire.failed or scope.cancel_called:
                wire.check()
                raise PersonalRuntimeUnavailable("Personal MCP unavailable", diagnostic=wire.diagnostic)
            return result
        except (TimeoutError, httpx2.TimeoutException):
            diagnostic = InvocationFailureDiagnostic(execution_mode="personal", stage="transport", reason="timeout")
        except PersonalRuntimeUnavailable as error:
            diagnostic = error.diagnostic
        except Exception:
            diagnostic = wire.diagnostic
        if wire.authorization_rejected:
            raise PersonalAuthorizationRejected("Personal MCP unavailable", diagnostic=InvocationFailureDiagnostic(execution_mode="personal", stage="authorization", reason="authorization_rejected")) from None
        if wire.failed:
            diagnostic = wire.diagnostic
        elif anyio.current_time() >= wire.deadline:
            diagnostic = InvocationFailureDiagnostic(execution_mode="personal", stage="transport", reason="timeout")
        raise PersonalRuntimeUnavailable("Personal MCP unavailable", diagnostic=diagnostic) from None

    def _bridge(self, wire: OperationState) -> PersonalHttpTransport:
        pool = httpcore2.AsyncConnectionPool(
            ssl_context=self._ssl_context, max_connections=2, max_keepalive_connections=0,
            retries=0, http1=True, http2=False,
            network_backend=PinnedPublicNetworkBackend(self._resolver, self._backend_factory(), wire.check, wire.target.access_token),
        )
        return PersonalHttpTransport(pool, wire)

    def _client(self, bridge: PersonalHttpTransport, target: PersonalRuntimeTarget, budget: float) -> Client:
        def client_factory(**sdk_options: object) -> httpx2.AsyncClient:
            return httpx2.AsyncClient(
                transport=bridge, trust_env=False, follow_redirects=False, auth=None,
                timeout=httpx2.Timeout(budget),
                headers={"Authorization": f"Bearer {target.access_token.get_secret_value()}"},
            )
        transport = StreamableHttpTransport(target.endpoint_url, httpx_client_factory=client_factory, auth=None)
        return Client(transport, mode="legacy", timeout=budget, init_timeout=budget, cache=False)

    async def _session(self, client: Client, bridge: PersonalHttpTransport, wire: OperationState) -> dict[str, object]:
        try:
            await client.__aenter__()
            inventory = await self._inventory(client, wire)
            if isinstance(wire.operation, PersonalToolCall):
                approved = PersonalToolInventory.model_validate(inventory)
                matches = tuple(tool for tool in approved.tools if tool.identity.downstream_name == wire.operation.tool_name)
                if len(matches) != 1 or contract_fingerprint(matches[0]) != wire.operation.expected_fingerprint:
                    wire.fail(InvocationFailureDiagnostic(execution_mode="personal", stage="transport", reason="contract_mismatch"))
                validate_contract_schema(matches[0].input_schema)
                if matches[0].output_schema_status == "present":
                    validate_contract_schema(matches[0].output_schema)
                wire.preflight_complete = True
                result = await self._call(client, wire.operation)
            else:
                result = inventory
            wire.check()
            if contains_secret(result, wire.target.access_token.get_secret_value()):
                wire.fail()
            return result
        finally:
            wire.cleaning_up = True
            try:
                with anyio.move_on_after(0.25, shield=True):
                    await client.close()
            finally:
                await bridge.aclose()

    async def _call(self, client: Client, operation: PersonalToolCall) -> dict[str, object]:
        raw = await client.session.send_request(
            types.CallToolRequest(params=types.CallToolRequestParams(name=operation.tool_name, arguments=operation.arguments)),
            StrictCallToolResult,
        )
        return PersonalToolResult(result=raw.model_dump(mode="json", by_alias=True, exclude_none=True)).model_dump(mode="json")

    async def _inventory(self, client: Client, state: OperationState) -> dict[str, object]:
        tools: list[DiscoveredTool] = []
        names: set[str] = set()
        for page in range(self._limits.maximum_tool_pages):
            params = types.PaginatedRequestParams(cursor=state.expected_cursor) if page else None
            response = await client.session.list_tools(params=params)
            for tool in response.tools:
                if len(tools) >= 256 or tool.name in names or len(tool.name) > 128:
                    state.fail()
                names.add(tool.name)
                mapped = {
                    "identity": {"connector_id": state.target.key.connector_id, "downstream_name": tool.name},
                    "title": tool.title or tool.name,
                    "description": tool.description or "",
                    "input_schema": tool.input_schema,
                    "annotations": tool.annotations.model_dump(mode="json", by_alias=True, exclude_none=True) if tool.annotations is not None else {},
                    "icons": tuple(icon.model_dump(mode="json", by_alias=True, exclude_none=True) for icon in tool.icons or ()),
                    "meta": tool.meta or {},
                    "execution": tool.execution.model_dump(mode="json", by_alias=True, exclude_none=True) if tool.execution is not None else {},
                    "output_schema_status": "absent" if tool.output_schema is None else "present",
                }
                if tool.output_schema is not None:
                    mapped["output_schema"] = tool.output_schema
                tools.append(TypeAdapter(DiscoveredTool).validate_python(mapped))
            if response.next_cursor is None:
                return PersonalToolInventory(tools=tuple(tools)).model_dump(mode="json")
            if not response.next_cursor or response.next_cursor in state.cursors:
                state.fail()
            state.expected_cursor = response.next_cursor
        state.fail()
