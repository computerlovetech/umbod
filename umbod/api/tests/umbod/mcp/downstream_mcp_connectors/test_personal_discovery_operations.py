import asyncio
from dataclasses import replace
from fastmcp.server.auth import AccessToken
from mcp.server.auth.middleware.auth_context import auth_context_var
from mcp.server.auth.middleware.bearer_auth import AuthenticatedUser
from tests.umbod.mcp.test_personal_caller import _settings
from umbod.mcp.connectors.downstream_mcp.personal_runtime import McpPersonalCallerProvider, McpPersonalToolRuntime
from typing import cast
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from umbod.core.persistence import ReadSession
from umbod.core.persistence.ports import RowT, KeyT, ResultT
from umbod.core.persistence.query import Table, Query

import pytest
from fastmcp import Client, FastMCP
from fastmcp.server.middleware import AuthMiddleware

from tests.support.native_tool_states import enabled_native_tool_states
from tests.umbod.core.downstream_mcp_connectors.test_personal_runtime_authorizations import RuntimeCase, runtime_case
from tests.umbod.core.downstream_mcp_connectors.test_personal_tools_s3_contracts import approved_tool
from tests.umbod.mcp.downstream_mcp_connectors.personal_runtime_support import execution_case
from tests.umbod.mcp.downstream_mcp_connectors.test_personal_execution_pipeline import InvocationLog, provider_for
from tests.umbod.mcp.downstream_mcp_connectors.signal_support import invocation_signals
from umbod.core.configuration import InMemoryConnectorCurrentConfigurationStore
from umbod.core.connectors.downstream_mcp.personal_connections.models import SetPersonalConnectionEnabled
from umbod.core.connectors.downstream_mcp.personal_connections.runtime_models import PersonalToolInventory
from umbod.core.connectors.downstream_mcp.personal_tools.models import PersonalToolDiscoveryQuery, PersonalToolRecord
from umbod.core.connectors.downstream_mcp.personal_tools.ports import PersonalToolDiscoveryReader
from umbod.core.connectors.downstream_mcp.personal_tools.service import PersonalToolDiscoveryService
from umbod.core.invocation import ConnectorInvocation, PermitAllConnectorInvocationPolicy
from umbod.core.permissions import InMemoryGroupConnectorToolPermissions
from umbod.mcp.connectors.downstream_mcp.personal_discovery import PersonalDiscoveryOperations
from umbod.mcp.connectors.downstream_mcp.personal_runtime import PersonalDiscoveryMiddleware, PersonalToolReservationMiddleware, personal_tool_permission_check
from umbod.mcp.connectors.downstream_mcp.provider import reset_request_connector_scope, set_request_connector_scope
from umbod.mcp.connectors.native.tools import RuntimeConnectorToolRegistry, register_connector_tools
from umbod.mcp.metrics import InMemoryMcpMetricsRecorder
from umbod.mcp.signals import SignalToolExecutionPipelineFactory

__all__ = ["runtime_case"]


class CountingReader:
    def __init__(self, reader: PersonalToolDiscoveryReader) -> None:
        self.reader = reader
        self.queries: list[PersonalToolDiscoveryQuery] = []

    async def read(self, query: PersonalToolDiscoveryQuery) -> tuple[PersonalToolRecord, ...]:
        self.queries.append(query)
        return await self.reader.read(query)


class PausedReader(CountingReader):
    def __init__(self, reader: PersonalToolDiscoveryReader) -> None:
        super().__init__(reader)
        self.started = asyncio.Event()
        self.resume = asyncio.Event()
        self.cancelled = asyncio.Event()

    async def read(self, query: PersonalToolDiscoveryQuery) -> tuple[PersonalToolRecord, ...]:
        self.queries.append(query)
        self.started.set()
        try:
            await self.resume.wait()
        except asyncio.CancelledError:
            self.cancelled.set()
            raise
        return await self.reader.read(query)


class FailingOnceReader(CountingReader):
    async def read(self, query: PersonalToolDiscoveryQuery) -> tuple[PersonalToolRecord, ...]:
        self.queries.append(query)
        if len(self.queries) == 1:
            raise RuntimeError("Owner state unavailable")
        return await self.reader.read(query)


class PausedReadSession:
    def __init__(self, session: ReadSession, started: asyncio.Event, resume: asyncio.Event) -> None:
        self.session = session
        self.started = started
        self.resume = resume

    async def find_one(self, table: Table[RowT, KeyT], query: Query[RowT, ResultT]) -> ResultT | None:
        result = await self.session.find_one(table, query)
        self.started.set()
        await self.resume.wait()
        return result

    async def find_many(self, table: Table[RowT, KeyT], query: Query[RowT, ResultT]) -> Sequence[ResultT]:
        return await self.session.find_many(table, query)


@pytest.mark.asyncio
@pytest.mark.parametrize("tool_count", (1, 40))
@pytest.mark.parametrize("exposure", ("flat", "scoped", "gateway", "codemode"))
async def test_public_discovery_reads_one_inventory_with_outer_authorization(runtime_case: RuntimeCase, tool_count: int, exposure: str, monkeypatch: pytest.MonkeyPatch) -> None:
    execution = await execution_case(runtime_case)
    execution.transport.inventories[runtime_case.query.key] = PersonalToolInventory(tools=tuple(approved_tool(f"read_{index}") for index in range(tool_count)))
    await PersonalToolDiscoveryService(runtime_case.store, runtime_case.bundle.personal_tool_access, execution.transport, lambda: runtime_case.query.now).discover(runtime_case.query)
    provider = await provider_for(execution, PermitAllConnectorInvocationPolicy(), InvocationLog())
    async with provider.discovery_operation() as operation:
        owner = operation.owner
    reader = CountingReader(owner.reader)
    owner.reader = reader
    public = FastMCP("personal-budget", middleware=[PersonalDiscoveryMiddleware(provider), AuthMiddleware(auth=personal_tool_permission_check(lambda context: True)), PersonalToolReservationMiddleware(provider)])
    if exposure in ("flat", "scoped"):
        public.add_provider(provider)
    else:
        signals = invocation_signals(InMemoryMcpMetricsRecorder())
        await register_connector_tools(public, signals=signals, execution_pipelines=SignalToolExecutionPipelineFactory(signals, PermitAllConnectorInvocationPolicy()), connector_registrations=[], connector_configuration_store=InMemoryConnectorCurrentConfigurationStore(), connector_publishing_store=runtime_case.bundle.publishing, connector_tool_mappings=[], connector_tool_runtime_state_store=enabled_native_tool_states(), connector_tool_exposure_mode=exposure)
        cast(RuntimeConnectorToolRegistry, public.connector_tool_registry).add_gateway_provider(provider)

    async def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("Discovery must not read authoritative stores")

    for store, method in ((runtime_case.bundle.definitions, "list"), (runtime_case.bundle.definitions, "get"), (runtime_case.bundle.credentials, "get"), (runtime_case.bundle.catalogs, "get"), (runtime_case.bundle.publishing, "is_published")):
        monkeypatch.setattr(store, method, forbidden)
    read_session = runtime_case.database.read_session
    sessions: list[object] = []

    @asynccontextmanager
    async def counted_read_session() -> AsyncIterator[ReadSession]:
        async with read_session() as session:
            sessions.append(session)
            yield session

    def forbidden_session(*args: object, **kwargs: object) -> None:
        raise AssertionError("Discovery must not reserve a writer session")

    monkeypatch.setattr(runtime_case.database, "read_session", counted_read_session)
    monkeypatch.setattr(runtime_case.database, "session", forbidden_session)
    marker = set_request_connector_scope("personal" if exposure == "scoped" else "")
    try:
        async with Client(public) as client:
            reader.queries.clear()
            sessions.clear()
            await client.list_tools()
            assert len(reader.queries) == 1
            assert len(sessions) == 1
            reader.queries.clear()
            sessions.clear()
            if exposure in ("flat", "scoped"):
                tools = await client.list_tools()
                assert len(tools) == tool_count
            else:
                result = await client.call_tool_mcp("search_tools", {"query": "read", "limit": 50})
                assert not result.is_error
                assert len(result.structured_content["matches"]) == tool_count
    finally:
        reset_request_connector_scope(marker)
    assert len(reader.queries) == 1
    assert len(sessions) == 1
    assert execution.transport.calls == []


@pytest.mark.asyncio
async def test_nested_discovery_singleflights_and_evaluates_current_connector_grants(runtime_case: RuntimeCase) -> None:
    execution = await execution_case(runtime_case)
    provider = await provider_for(execution, PermitAllConnectorInvocationPolicy(), InvocationLog())
    async with provider.discovery_operation() as initial:
        owner = initial.owner
    reader = PausedReader(owner.reader)
    owner.reader = reader
    async with provider.discovery_operation() as operation:
        first = asyncio.create_task(provider.list_tools())
        await reader.started.wait()
        second = asyncio.create_task(provider.eligible_search_candidates())
        reader.resume.set()
        assert len(await first) == len(await second) == 1
        assert await operation.contains(execution.command)
        owner.permissions.replace_group_permissions({}, {})
        assert not await operation.contains(execution.command)
        assert await provider.list_tools() == []
    assert len(reader.queries) == 1


@pytest.mark.asyncio
async def test_cancelled_discovery_resets_context_and_next_operation_reloads(runtime_case: RuntimeCase) -> None:
    execution = await execution_case(runtime_case)
    provider = await provider_for(execution, PermitAllConnectorInvocationPolicy(), InvocationLog())
    async with provider.discovery_operation() as initial:
        owner = initial.owner
    reader = PausedReader(owner.reader)
    owner.reader = reader
    retained = []

    async def discover() -> None:
        async with provider.discovery_operation() as operation:
            retained.append(operation)
            await asyncio.gather(provider.list_tools(), provider.eligible_search_candidates())

    task = asyncio.create_task(discover())
    await reader.started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert reader.cancelled.is_set()
    assert not retained[0].active
    assert await retained[0].records() == ()
    reader.resume.set()
    assert len(await provider.list_tools()) == 1
    assert len(reader.queries) == 2


@pytest.mark.asyncio
async def test_operation_application_and_connector_scopes_are_isolated(runtime_case: RuntimeCase) -> None:
    execution = await execution_case(runtime_case)
    provider = await provider_for(execution, PermitAllConnectorInvocationPolicy(), InvocationLog())
    async with provider.discovery_operation() as operation:
        owner = operation.owner
    reader = CountingReader(owner.reader)
    owner.reader = reader
    second = PersonalDiscoveryOperations(owner.runtime, owner.callers, reader, owner.permissions, owner.clock, owner.permission_policy)
    async with owner.operation("") as root:
        assert len(await root.records()) == 1
        async with second.operation("") as other_application:
            assert other_application is not root
            assert len(await other_application.records()) == 1
        async with owner.operation("other") as other_scope:
            assert await other_scope.records() == ()
        async with owner.operation("") as nested:
            assert nested is root
    assert len(reader.queries) == 2


@pytest.mark.asyncio
async def test_writer_can_disable_owner_while_discovery_snapshot_is_paused(runtime_case: RuntimeCase, monkeypatch: pytest.MonkeyPatch) -> None:
    execution = await execution_case(runtime_case)
    provider = await provider_for(execution, PermitAllConnectorInvocationPolicy(), InvocationLog())
    started = asyncio.Event()
    resume = asyncio.Event()
    read_session = runtime_case.database.read_session

    @asynccontextmanager
    async def paused_read_session() -> AsyncIterator[ReadSession]:
        async with read_session() as session:
            yield PausedReadSession(session, started, resume)

    monkeypatch.setattr(runtime_case.database, "read_session", paused_read_session)
    listing = asyncio.create_task(provider.list_tools())
    await started.wait()
    try:
        await asyncio.wait_for(runtime_case.bundle.personal_connections.set_enabled(SetPersonalConnectionEnabled(key=runtime_case.query.key, enabled=False)), timeout=2)
    finally:
        resume.set()
    assert len(await listing) == 1
    assert await provider.list_tools() == []


@pytest.mark.asyncio
async def test_failed_owner_read_cleans_up_and_next_operation_retries(runtime_case: RuntimeCase) -> None:
    execution = await execution_case(runtime_case)
    provider = await provider_for(execution, PermitAllConnectorInvocationPolicy(), InvocationLog())
    async with provider.discovery_operation() as operation:
        owner = operation.owner
    reader = FailingOnceReader(owner.reader)
    owner.reader = reader
    with pytest.raises(RuntimeError, match="Owner state unavailable"):
        await provider.list_tools()
    assert len(await provider.list_tools()) == 1
    assert len(reader.queries) == 2


@pytest.mark.asyncio
async def test_personal_discovery_denies_individual_tool_grants_without_connector_grant(runtime_case: RuntimeCase) -> None:
    execution = await execution_case(runtime_case)
    provider = await provider_for(execution, PermitAllConnectorInvocationPolicy(), InvocationLog())
    async with provider.discovery_operation() as operation:
        owner = operation.owner
    owner.permissions.replace_group_permissions({}, {})
    for group in runtime_case.query.group_ids:
        owner.permissions.grant_tool(group, "personal", "read")
    reader = CountingReader(owner.reader)
    owner.reader = reader
    assert await provider.list_tools() == []
    assert reader.queries == []
    for group in runtime_case.query.group_ids:
        owner.permissions.grant_connector(group, "personal")
    assert len(await provider.list_tools()) == 1


class PausedInvocationPolicy:
    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.resume = asyncio.Event()

    async def evaluate(self, invocation: ConnectorInvocation) -> None:
        self.started.set()
        await self.resume.wait()


@pytest.mark.asyncio
async def test_public_execution_rechecks_admission_after_discovery_authorization_is_revoked(runtime_case: RuntimeCase) -> None:
    execution = await execution_case(runtime_case)
    settings = _settings(namespace="trusted")
    settings = settings.model_copy(update={"mcp": settings.mcp.model_copy(update={"permission_group_claim": "groups"})})
    callers = McpPersonalCallerProvider(settings)
    runtime = McpPersonalToolRuntime(callers, runtime_case.bundle.personal_tool_access, execution.transport, lambda: runtime_case.query.now)
    policy = PausedInvocationPolicy()
    provider = await provider_for(replace(execution, runtime=runtime, contexts=callers), policy, InvocationLog())
    public = FastMCP("paused-personal-execution", providers=[provider], middleware=[PersonalDiscoveryMiddleware(provider), AuthMiddleware(auth=personal_tool_permission_check(lambda context: True)), PersonalToolReservationMiddleware(provider)])
    identity = AuthenticatedUser(AccessToken(token="owner-upstream", client_id="client", scopes=[], claims={"sub": "owner", "groups": ["team"]}))
    marker = auth_context_var.set(identity)
    try:
        async with Client(public) as client:
            await client.list_tools()
            call = asyncio.create_task(client.call_tool_mcp("Personal_read", {"value": "same"}))
            await policy.started.wait()
            try:
                await runtime_case.bundle.personal_connections.set_enabled(SetPersonalConnectionEnabled(key=runtime_case.query.key, enabled=False))
            finally:
                policy.resume.set()
            assert (await call).is_error
    finally:
        auth_context_var.reset(marker)
    assert execution.transport.calls == []


def test_explicit_connector_grants_exclude_tool_only_grants() -> None:
    from umbod.core.callers import GroupMembership

    permissions = InMemoryGroupConnectorToolPermissions(group_claim_fields=("groups",))
    permissions.grant_tool("team", "tool-only", "read")
    permissions.grant_connector("team", "connector")
    membership = GroupMembership(group_ids=("team",))
    assert permissions.allowed_connector_ids(membership) == {"tool-only", "connector"}
    assert permissions.explicitly_granted_connector_ids(membership) == {"connector"}
    permissions.replace_group_permissions({}, {})
    assert permissions.explicitly_granted_connector_ids(membership) == set()
