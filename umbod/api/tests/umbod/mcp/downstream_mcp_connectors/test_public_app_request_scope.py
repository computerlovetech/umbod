from umbod.mcp.telemetry.composition import create_configured_mcp_telemetry
from umbod.mcp.runtime_adapters import create_configured_downstream_client_factory, create_configured_openapi_runtime_adapters
from umbod.core.configuration.persistence import AuthenticatedTextCipher
from umbod.core.publishing.factories import create_connector_publishing_store
from umbod.core.publishing.stores.schema import PUBLICATION_STATE_TABLE
from umbod.core.publishing.stores.service import ConnectorPublishingStoreService
from umbod.core.invocation.tools.database_configuration_mutation import DatabaseConnectorToolConfigurationMutationAdapter
from umbod.core.activation import CapabilityRef, create_capability_activation_store
from umbod.core.connectors.downstream_mcp.stores import CONNECTOR_CREDENTIAL_TABLE, CONNECTOR_DEFINITION_TABLE, ConnectorDefinitionStoreService, EncryptedCredentialStoreService, TOOL_CATALOG_TABLE, ToolCatalogStoreService
from umbod.infrastructure import ConfiguredPersistenceRuntimeProvider
from tests.persistence_runtime import create_inmemory_runtime, create_sqlite_runtime, prepared_sqlite_runtime
import asyncio
import json
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, AsyncIterator
from unittest.mock import AsyncMock, Mock

from umbod.core.filesystem.browsing import FilesystemBrowsing, NodeSummary
from umbod.core.filesystem.models import NodeKind, NodeMetadata, RootParent
from umbod.mcp.filesystem import DatabaseFilesystemServiceFactory
import httpx
import pytest
import pytest_asyncio
from fastmcp import Client, FastMCP
from fastmcp.client.client import CallToolResult
from fastmcp.client.elicitation import ElicitResult
from fastmcp.client.transports import FastMCPTransport
from fastmcp.server.auth.auth import AccessToken
from mcp.server.auth.middleware.auth_context import AuthenticatedUser, auth_context_var
from mcp.types import InputRequiredResult
from umbod.config import ConnectorStoreConfig
from tests.support.configuration import InMemoryConnectorCurrentConfigurationStore
from umbod.core.connectors.native.runtime import ConnectorRuntime
from umbod.core.invocation.tools.configuration_mutation import ConnectorToolConfigurationMutation, ConnectorToolInvocationPolicyChange
from umbod.core.activation import ActivationStatus
from umbod.core.connectors.downstream_mcp.models import DiscoveredToolWithOutputSchema, NoAuthConnectorDefinition, NoAuthCredentialState, ToolCatalogSnapshot, ToolIdentity
from umbod.core.connectors.downstream_mcp.stores import ReplaceToolCatalog, SaveConnectorDefinition, SaveCredential
from umbod.core.connectors.downstream_mcp.probe import DiscoverDownstreamTools
from umbod.mcp.context import PublicAppConfig, PublicAppRuntimeContext
from umbod.mcp.public_app import build_starlette_app, create_runtime_context
from umbod.mcp.runtime_options import ConnectorRuntimeSourceStores, StoreBackedConnectorRuntimeStateSourceStrategy
from umbod.mcp.settings import MCPAppSettings, MCPSettings
CONNECTOR_ID = 'scope-test'
PUBLIC_PATH = '/mcp/proxies/scope-test'
DOWNSTREAM_TOOL_NAMES = ('search_tools', 'execute_code')

class InMemoryServerClientFactory:

    def __init__(self, server: FastMCP) -> None:
        self._server = server

    def create(self, command: DiscoverDownstreamTools) -> Client:
        return Client(self._server)

async def _persist_catalog(database_path: str) -> None:
    await prepared_sqlite_runtime(database_path)
    await ConnectorDefinitionStoreService(create_sqlite_runtime(database_path).database, CONNECTOR_DEFINITION_TABLE).save(SaveConnectorDefinition(definition=NoAuthConnectorDefinition(connector_id=CONNECTOR_ID, display_name='Scope test', tool_name_prefix='scope_test', endpoint_url='https://scope.example.test/mcp', public_path=PUBLIC_PATH)))
    await EncryptedCredentialStoreService(create_sqlite_runtime(database_path).database, CONNECTOR_CREDENTIAL_TABLE, AuthenticatedTextCipher('test-secret')).save(SaveCredential(credential=NoAuthCredentialState(connector_id=CONNECTOR_ID)))
    tools = tuple((DiscoveredToolWithOutputSchema(identity=ToolIdentity(connector_id=CONNECTOR_ID, downstream_name=name), title=name, description=f'Downstream {name}', input_schema={'type': 'object', 'properties': {}}, output_schema={'type': 'object'}) for name in DOWNSTREAM_TOOL_NAMES))
    await ToolCatalogStoreService(create_sqlite_runtime(database_path).database, TOOL_CATALOG_TABLE).replace(ReplaceToolCatalog(snapshot=ToolCatalogSnapshot(connector_id=CONNECTOR_ID, discovered_at=datetime(2026, 1, 1, tzinfo=UTC), tools=tools)))
    database = (await prepared_sqlite_runtime(database_path)).database
    publishing_store = await create_connector_publishing_store(database)
    await publishing_store.publish_connector(CONNECTOR_ID)
    activation_store = await create_capability_activation_store(database)
    for name in DOWNSTREAM_TOOL_NAMES:
        await activation_store.set_status(CapabilityRef(connector_kind="downstream_mcp", connector_id=CONNECTOR_ID, capability_kind="tool", capability_key=name), ActivationStatus.ENABLED)

def _request(identifier: int, method: str, parameters: dict[str, Any]) -> dict[str, Any]:
    return {'jsonrpc': '2.0', 'id': identifier, 'method': method, 'params': parameters}

async def _post(client: httpx.AsyncClient, path: str, payload: dict[str, Any]) -> dict[str, Any]:
    response = await client.post(path, json=payload, headers={'Accept': 'application/json, text/event-stream', 'Content-Type': 'application/json'})
    assert response.status_code == 200
    if response.headers.get('content-type', '').startswith('text/event-stream'):
        data_line = next((line for line in response.text.splitlines() if line.startswith('data: ')))
        parsed = json.loads(data_line.removeprefix('data: '))
        if not isinstance(parsed, dict):
            raise TypeError('MCP response must be an object')
        return parsed
    parsed = response.json()
    if not isinstance(parsed, dict):
        raise TypeError('MCP response must be an object')
    return parsed

@pytest.mark.asyncio
async def test_proxy_request_scope_does_not_leak_into_flat_root_tools_list(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    database_path = str(tmp_path / 'request-scope.sqlite3')
    await _persist_catalog(database_path)
    settings = MCPAppSettings(mcp=MCPSettings(metrics_enabled=False, connector_tool_exposure_mode='flat', downstream_discovery_enabled=False, stateless_http=True, _env_file=None), connector_store=ConnectorStoreConfig(type='sqlite', sqlite_path=database_path), connector_security={'configuration_secret': 'test-secret'}, _env_file=None)
    runtime = ConnectorRuntime(connector_registrations=[], connector_configuration_store=InMemoryConnectorCurrentConfigurationStore(), connector_publishing_store=ConnectorPublishingStoreService(create_inmemory_runtime().database, PUBLICATION_STATE_TABLE), connector_tool_mappings=[])
    persistence_runtime = ConfiguredPersistenceRuntimeProvider(settings.connector_store).create()
    await persistence_runtime.readiness.ensure_ready()
    config = PublicAppConfig(settings=settings, telemetry=create_configured_mcp_telemetry(settings), connector_runtime=runtime, source_stores=ConnectorRuntimeSourceStores(), configured_source_strategy=StoreBackedConnectorRuntimeStateSourceStrategy(), stateless_http=True, api_base_url=None, persistence_runtime=persistence_runtime)
    context = await create_runtime_context(config, downstream_client_factory=await create_configured_downstream_client_factory(config.settings, config.persistence_runtime.database), openapi_adapters=create_configured_openapi_runtime_adapters(config.settings))
    browsing = Mock(spec=FilesystemBrowsing)
    browsing.get_root = AsyncMock(return_value=NodeSummary(
        id='00000000-0000-0000-0000-000000000001', parent_id=RootParent(),
        name='/', kind=NodeKind.DIRECTORY,
        metadata=NodeMetadata(content_type='application/octet-stream', attributes={}),
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        updated_at=datetime(2026, 1, 1, tzinfo=UTC), revision=1,
    ))
    service_factory = Mock(return_value=browsing)
    monkeypatch.setattr(DatabaseFilesystemServiceFactory, 'browsing', service_factory)
    app = await build_starlette_app(context)
    transport = httpx.ASGITransport(app=app)
    async with app.router.lifespan_context(app):
        for group in ('test', settings.mcp.test_user_group):
            context.group_permission_runtime_state.grant_connector(group, CONNECTOR_ID)
            for name in DOWNSTREAM_TOOL_NAMES:
                context.group_permission_runtime_state.grant_tool(group, CONNECTOR_ID, name)
        async with httpx.AsyncClient(transport=transport, base_url='http://test', headers={'Authorization': f'Bearer {settings.mcp.test_bearer_token}'}) as client:
            await _post(client, PUBLIC_PATH, _request(1, 'initialize', {}))
            proxy_response = await _post(client, PUBLIC_PATH, _request(2, 'tools/list', {}))
            (root_response, concurrent_proxy_response) = await asyncio.gather(_post(client, '/mcp', _request(3, 'tools/list', {})), _post(client, PUBLIC_PATH, _request(4, 'tools/list', {})))
            refreshed_root_response = await _post(client, '/mcp', _request(5, 'tools/list', {}))
            allowed_response = await _post(client, '/mcp', _request(6, 'tools/call', {'name': 'get_filesystem_root', 'arguments': {}}))
            assert allowed_response['result']['structuredContent']['id'] == '00000000-0000-0000-0000-000000000001'
            service_factory.assert_called_once_with()
            forbidden_response = await _post(client, PUBLIC_PATH, _request(7, 'tools/call', {'name': 'get_filesystem_root', 'arguments': {}}))
    service_factory.assert_called_once_with()
    assert 'error' in forbidden_response or forbidden_response['result'].get('isError') is True
    proxy_names = {tool['name'] for tool in proxy_response['result']['tools']}
    concurrent_proxy_names = {tool['name'] for tool in concurrent_proxy_response['result']['tools']}
    expected_root_names = {f'scope_test_{name}' for name in DOWNSTREAM_TOOL_NAMES} | {"get_filesystem_root", "get_filesystem_node", "list_filesystem_children", "create_filesystem_file", "create_filesystem_directory"}
    root_names = {tool['name'] for tool in root_response['result']['tools']}
    refreshed_root_names = {tool['name'] for tool in refreshed_root_response['result']['tools']}
    assert proxy_names == set(DOWNSTREAM_TOOL_NAMES)
    assert concurrent_proxy_names == set(DOWNSTREAM_TOOL_NAMES)
    assert expected_root_names == root_names
    assert not set(DOWNSTREAM_TOOL_NAMES) & root_names
    assert expected_root_names == refreshed_root_names
    assert not set(DOWNSTREAM_TOOL_NAMES) & refreshed_root_names

class RecordingClientSession:

    def __init__(self, session: Any, observed_states: list[tuple[str | None, str | None]]) -> None:
        self._session = session
        self._observed_states = observed_states

    async def call_tool(self, *args: object, **kwargs: Any) -> Any:
        result = await self._session.call_tool(*args, **kwargs)
        returned_state = result.request_state if isinstance(result, InputRequiredResult) else None
        request_state = kwargs.get('request_state')
        self._observed_states.append((request_state if isinstance(request_state, str) else None, returned_state))
        return result

    def __getattr__(self, name: str) -> Any:
        return getattr(self._session, name)

class RecordingFastMCPTransport(FastMCPTransport):

    def __init__(self, server: FastMCP) -> None:
        super().__init__(server)
        self.observed_states: list[tuple[str | None, str | None]] = []

    @asynccontextmanager
    async def connect_session(self, **kwargs: Any) -> AsyncIterator[RecordingClientSession]:
        async with super().connect_session(**kwargs) as session:
            yield RecordingClientSession(session, self.observed_states)

class ExecutionRecorder:

    def __init__(self) -> None:
        self.count = 0

    async def search_tools(self) -> dict[str, bool]:
        self.count += 1
        return {'executed': True}


class DownstreamApprovalHarness:

    def __init__(self, context: PublicAppRuntimeContext, mutation_adapter: DatabaseConnectorToolConfigurationMutationAdapter, ask_revision: int, recorder: ExecutionRecorder) -> None:
        self.context = context
        self.mutation_adapter = mutation_adapter
        self.ask_revision = ask_revision
        self.recorder = recorder

    @property
    def execution_count(self) -> int:
        return self.recorder.count

    async def reject(self) -> CallToolResult:

        async def reject_handler(*args: object) -> ElicitResult[dict[str, bool]]:
            return ElicitResult(action='decline')
        async with Client(self.context.mcp, elicitation_handler=reject_handler) as client:
            return await client.call_tool('scope_test_search_tools', {}, raise_on_error=False)

    async def accept(self) -> tuple[CallToolResult, list[tuple[str | None, str | None]]]:

        async def accept_handler(*args: object) -> dict[str, bool]:
            return {'value': True}
        transport = RecordingFastMCPTransport(self.context.mcp)
        async with Client(transport, elicitation_handler=accept_handler) as client:
            result = await client.call_tool('scope_test_search_tools', {}, raise_on_error=False)
        return (result, transport.observed_states)

    async def switch_to_direct(self) -> None:
        await self.mutation_adapter.apply(ConnectorToolConfigurationMutation(connector_kind='downstream_mcp', connector_id=CONNECTOR_ID, policy_changes=(ConnectorToolInvocationPolicyChange(operation_name='search_tools', mode='direct', expected_revision=self.ask_revision),)))

    async def call_direct(self) -> CallToolResult:
        async with Client(self.context.mcp) as client:
            return await client.call_tool('scope_test_search_tools', {})

@pytest_asyncio.fixture
async def downstream_approval_harness(tmp_path: Path) -> AsyncIterator[DownstreamApprovalHarness]:
    database_path = str(tmp_path / 'approval-roundtrip.sqlite3')
    await _persist_catalog(database_path)
    settings = MCPAppSettings(mcp=MCPSettings(connector_tool_exposure_mode='flat', downstream_discovery_enabled=False, stateless_http=False, _env_file=None), connector_store=ConnectorStoreConfig(type='sqlite', sqlite_path=database_path), connector_security={'configuration_secret': 'test-secret', 'approval_state_key': 'acceptance-approval-state-key-with-sufficient-entropy'}, _env_file=None)
    runtime = ConnectorRuntime(connector_registrations=[], connector_configuration_store=InMemoryConnectorCurrentConfigurationStore(), connector_publishing_store=ConnectorPublishingStoreService(create_inmemory_runtime().database, PUBLICATION_STATE_TABLE), connector_tool_mappings=[])
    persistence_runtime = ConfiguredPersistenceRuntimeProvider(settings.connector_store).create()
    await persistence_runtime.readiness.ensure_ready()
    mutation_adapter = DatabaseConnectorToolConfigurationMutationAdapter(persistence_runtime.database)
    ask_result = await mutation_adapter.apply(ConnectorToolConfigurationMutation(connector_kind='downstream_mcp', connector_id=CONNECTOR_ID, policy_changes=(ConnectorToolInvocationPolicyChange(operation_name='search_tools', mode='ask', expected_revision=0),)))
    recorder = ExecutionRecorder()
    downstream = FastMCP('approval-downstream')
    downstream.tool(name='search_tools')(recorder.search_tools)
    config = PublicAppConfig(settings=settings, telemetry=create_configured_mcp_telemetry(settings), connector_runtime=runtime, source_stores=ConnectorRuntimeSourceStores(), configured_source_strategy=StoreBackedConnectorRuntimeStateSourceStrategy(), stateless_http=False, api_base_url=None, persistence_runtime=persistence_runtime)
    context = await create_runtime_context(config, downstream_client_factory=InMemoryServerClientFactory(downstream), openapi_adapters=create_configured_openapi_runtime_adapters(settings))
    harness = DownstreamApprovalHarness(context, mutation_adapter, ask_result.policies[0].revision, recorder)
    for group in ('test', settings.mcp.test_user_group):
        context.group_permission_runtime_state.grant_connector(group, CONNECTOR_ID)
        context.group_permission_runtime_state.grant_tool(group, CONNECTOR_ID, 'search_tools')
    token = auth_context_var.set(AuthenticatedUser(AccessToken(token=settings.mcp.test_bearer_token, client_id='acceptance-user', scopes=[], claims={'sub': 'acceptance-user', 'groups': [settings.mcp.test_user_group]})))
    yield harness
    auth_context_var.reset(token)

@pytest.mark.asyncio
async def test_persisted_ask_rejection_has_no_downstream_side_effects(downstream_approval_harness: DownstreamApprovalHarness) -> None:
    result = await downstream_approval_harness.reject()
    assert result.is_error is True
    assert downstream_approval_harness.execution_count == 0

@pytest.mark.asyncio
async def test_persisted_ask_sealed_fastmcp_continuation_echoes_state_and_executes_once(downstream_approval_harness: DownstreamApprovalHarness) -> None:
    (result, observed_states) = await downstream_approval_harness.accept()
    assert result.is_error is False
    assert result.structured_content == {'executed': True}
    assert downstream_approval_harness.execution_count == 1
    assert observed_states[0][0] is None
    sealed_state = observed_states[0][1]
    assert sealed_state is not None
    assert sealed_state.startswith('v1.')
    assert observed_states[1] == (sealed_state, None)

@pytest.mark.asyncio
async def test_persisted_ask_changed_to_direct_executes_once_without_elicitation(downstream_approval_harness: DownstreamApprovalHarness) -> None:
    await downstream_approval_harness.switch_to_direct()
    result = await downstream_approval_harness.call_direct()
    assert result.structured_content == {'executed': True}
    assert downstream_approval_harness.execution_count == 1


@pytest.mark.asyncio
async def test_separate_runtime_contexts_keep_injected_execution_factories_isolated(tmp_path: Path) -> None:
    database_path = str(tmp_path / 'isolated-contexts.sqlite3')
    await _persist_catalog(database_path)
    settings = MCPAppSettings(mcp=MCPSettings(metrics_enabled=False, connector_tool_exposure_mode='flat', downstream_discovery_enabled=False, _env_file=None), connector_store=ConnectorStoreConfig(type='sqlite', sqlite_path=database_path), connector_security={'configuration_secret': 'test-secret'}, _env_file=None)
    recorders = (ExecutionRecorder(), ExecutionRecorder())
    contexts: list[PublicAppRuntimeContext] = []
    try:
        for recorder in recorders:
            persistence = ConfiguredPersistenceRuntimeProvider(settings.connector_store).create()
            await persistence.readiness.ensure_ready()
            runtime = ConnectorRuntime(connector_registrations=[], connector_configuration_store=InMemoryConnectorCurrentConfigurationStore(), connector_publishing_store=ConnectorPublishingStoreService(persistence.database, PUBLICATION_STATE_TABLE), connector_tool_mappings=[])
            downstream = FastMCP('isolated-downstream')
            downstream.tool(name='search_tools')(recorder.search_tools)
            adapters = create_configured_openapi_runtime_adapters(settings)
            config = PublicAppConfig(settings=settings, telemetry=create_configured_mcp_telemetry(settings), connector_runtime=runtime, source_stores=ConnectorRuntimeSourceStores(), configured_source_strategy=StoreBackedConnectorRuntimeStateSourceStrategy(), stateless_http=False, api_base_url=None, persistence_runtime=persistence)
            context = await create_runtime_context(config, downstream_client_factory=InMemoryServerClientFactory(downstream), openapi_adapters=adapters)
            contexts.append(context)
            assert context.mcp.openapi_outbound_http_client_factory is adapters.outbound_http_client_factory
            context.group_permission_runtime_state.grant_connector(settings.mcp.test_user_group, CONNECTOR_ID)
            context.group_permission_runtime_state.grant_tool(settings.mcp.test_user_group, CONNECTOR_ID, 'search_tools')
        token = auth_context_var.set(AuthenticatedUser(AccessToken(token=settings.mcp.test_bearer_token, client_id='isolation-user', scopes=[], claims={'sub': 'isolation-user', 'groups': [settings.mcp.test_user_group]})))
        try:
            for context, expected_counts in ((contexts[0], (1, 0)), (contexts[1], (1, 1)), (contexts[0], (2, 1))):
                async with Client(context.mcp) as client:
                    result = await client.call_tool('scope_test_search_tools', {})
                assert result.structured_content == {'executed': True}
                assert tuple(recorder.count for recorder in recorders) == expected_counts
        finally:
            auth_context_var.reset(token)
    finally:
        for context in contexts:
            await context.persistence_runtime.shutdown()
