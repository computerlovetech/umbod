from umbod.mcp.runtime_adapters import create_configured_openapi_runtime_adapters
from umbod.core.permissions.factories import create_group_permission_store
from umbod.infrastructure import AppPersistenceRuntime
from umbod.core.persistence import Database
from umbod.rest.factories import ConnectorApiDependencyFactories
from umbod.mcp.runtime_options import StoreBackedConnectorRuntimeStateSourceStrategy
from contextlib import AsyncExitStack
import httpx
from dataclasses import replace
from pathlib import Path
from typing import Any
import httpx2
import jwt
import pytest
from fastapi import FastAPI
from fastmcp import Client, FastMCP
from fastmcp.client.transports import StreamableHttpTransport
from fastmcp.tools import ToolResult
from starlette.applications import Starlette
from umbod.config import AppConfig, McpConfig
from umbod.core.connectors.downstream_mcp.probe import DiscoverDownstreamTools
from umbod.core.connectors.downstream_mcp.probe import DiscoveredCapabilities, DiscoveredCapabilityTool, ProbeCapabilities, ScriptedDownstreamMcpProbe
from umbod.core.permissions import ConnectorToolRef, SaveGroupPermissionsRequest
from tests.mcp_fixtures import empty_connector_plugins
from umbod.mcp import public_app
from umbod.mcp.context import PublicAppRuntimeContext
from umbod.rest.connectors.downstream_mcp.dependencies import get_downstream_connector_probe
from umbod.rest.main import create_app_with_dependency_factories
from umbod.rest.settings import APISettings
TOOL_NAME = 'lookup_record'
TOOL_RESULT = {'record': {'id': 7, 'status': 'ready'}}
SECRET_CANARY = 'downstream-secret-canary'

class DeterministicDownstream:

    def __init__(self) -> None:
        self.invocations: list[dict[str, Any]] = []
        self.fail = False
        self.server = FastMCP('deterministic-downstream')
        self.server.tool(name=TOOL_NAME)(self._lookup_record)

    def create(self, command: DiscoverDownstreamTools) -> Client:
        return Client(self.server)

    async def _lookup_record(self, record_id: int) -> ToolResult:
        self.invocations.append({'record_id': record_id})
        if self.fail:
            raise RuntimeError(f'downstream failed with {SECRET_CANARY}')
        return ToolResult(structured_content=TOOL_RESULT)

class DownstreamHttpJourney:

    def __init__(self, app: Starlette, token: str, admin: httpx.AsyncClient, connector_id: str, downstream: DeterministicDownstream, context: PublicAppRuntimeContext) -> None:
        self.app = app
        self.token = token
        self.admin = admin
        self.connector_id = connector_id
        self.downstream = downstream
        self.context = context

    def grant_permissions(self) -> None:
        for group_id in ('engineering', 'test', self.context.settings.mcp.test_user_group):
            self.context.group_permission_runtime_state.grant_connector(group_id, self.connector_id)
            self.context.group_permission_runtime_state.grant_tool(group_id, self.connector_id, TOOL_NAME)

    def transport(self) -> StreamableHttpTransport:
        asgi_transport = httpx2.ASGITransport(app=self.app)

        def create_http_client(**kwargs: Any) -> httpx2.AsyncClient:
            return httpx2.AsyncClient(transport=asgi_transport, **kwargs)
        return StreamableHttpTransport('http://localhost/mcp', headers={'Authorization': f'Bearer {self.token}'}, httpx_client_factory=create_http_client)

def _settings(token: str) -> AppConfig:
    return AppConfig(rest={'metrics_enabled': False}, connector_store={'type': 'inmemory'}, mcp=McpConfig(metrics_enabled=False, auth_mode='single_test_user', test_bearer_token=token, permission_group_claim='groups', connector_tool_exposure_mode='flat', downstream_discovery_enabled=False, stateless_http=True), endpoints={'mcp_base_url': 'http://localhost'}, admin_authentication={'mode': 'simulation', 'simulated_admin': True}, connector_security={'configuration_secret': 'integration-configuration-secret', 'approval_state_key': 'integration-approval-state-key-with-sufficient-entropy'})

async def _grant_permission(database: Database, connector_id: str) -> None:
    store = await create_group_permission_store(database)
    await store.save_group_permissions(SaveGroupPermissionsRequest(group_id='engineering', connector_ids=(connector_id,), capabilities=(ConnectorToolRef(connector_id, TOOL_NAME).as_capability(),)))

async def _build_journey(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, runtime_resources: AsyncExitStack) -> DownstreamHttpJourney:
    availability_path = tmp_path / 'connector-availability.json'
    availability_path.write_text('{"connectors": []}', encoding='utf-8')
    monkeypatch.setenv('UMBOD_CONNECTOR_DEPLOYMENT_CONFIGURATION_PATH', str(availability_path))
    token = jwt.encode({'sub': 'engineer@example.test', 'email': 'engineer@example.test', 'groups': ['engineering']}, key='', algorithm='none')
    settings = _settings(token)
    monkeypatch.setattr(public_app, "load_connector_plugins", empty_connector_plugins)
    configured = await public_app.load_configured_public_app_config(settings)
    runtime_resources.push_async_callback(configured.persistence_runtime.shutdown)
    base = configured.persistence_runtime
    config = replace(
        configured,
        persistence_runtime=AppPersistenceRuntime(database=base.database, readiness=base.readiness),
        configured_source_strategy=StoreBackedConnectorRuntimeStateSourceStrategy(),
        api_base_url=None,
    )
    capability = DiscoveredCapabilityTool(name=TOOL_NAME, title='Lookup record', description='Look up a deterministic record', input_schema={'type': 'object', 'properties': {'record_id': {'type': 'integer'}}, 'required': ['record_id']}, output_schema={'type': 'object'})
    probe = ScriptedDownstreamMcpProbe((ProbeCapabilities(capabilities=DiscoveredCapabilities(tools=(capability,)), endpoint_url='https://downstream.example.test/mcp'),))
    admin_runtime = AppPersistenceRuntime(database=base.database, readiness=base.readiness)
    admin_factories = ConnectorApiDependencyFactories.from_settings(
        APISettings.model_validate(settings.model_dump()), admin_runtime, [],
    )
    admin_app = create_app_with_dependency_factories(admin_factories)
    mounted_admin = next((route.app for route in admin_app.routes if route.path == '/api/admin'))
    assert isinstance(mounted_admin, FastAPI)
    def provide_probe() -> ScriptedDownstreamMcpProbe:
        return probe

    mounted_admin.dependency_overrides[get_downstream_connector_probe] = provide_probe
    await runtime_resources.enter_async_context(admin_app.router.lifespan_context(admin_app))
    admin = await runtime_resources.enter_async_context(httpx.AsyncClient(
        transport=httpx.ASGITransport(app=admin_app), base_url="http://testserver",
    ))
    created = await admin.post('/api/admin/connectors/mcp', json={'metadata': {'display_name': 'Deterministic downstream', 'capability_description': 'Look up records', 'public_path': '/mcp/proxies/deterministic-downstream'}, 'configuration': {'endpoint_url': 'https://downstream.example.test/mcp', 'auth_mode': 'none'}})
    assert created.status_code == 201
    connector_id = created.json()['connector_id']
    published = await admin.put(f'/api/admin/connectors/mcp/{connector_id}/publication')
    enabled = await admin.put(f'/api/admin/connectors/mcp/{connector_id}/tools/activation', json={'tools': [{'tool_id': TOOL_NAME, 'activation_status': 'enabled'}]})
    assert published.status_code == 200
    assert enabled.status_code == 200
    await _grant_permission(base.database, connector_id)
    downstream = DeterministicDownstream()
    context = await public_app.create_runtime_context(config, downstream_client_factory=downstream, openapi_adapters=create_configured_openapi_runtime_adapters(settings))
    return DownstreamHttpJourney(await public_app.build_starlette_app(context), token, admin, connector_id, downstream, context)

@pytest.mark.asyncio
async def test_admin_registered_downstream_tool_roundtrips_through_public_mcp_http(runtime_resources: AsyncExitStack, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    journey = await _build_journey(tmp_path, monkeypatch, runtime_resources)
    async with journey.app.router.lifespan_context(journey.app):
        journey.grant_permissions()
        async with Client(journey.transport()) as client:
            tools = {tool.name for tool in await client.list_tools()}
            result = await client.call_tool('Deterministic_downstream_lookup_record', {'record_id': 7})
    assert 'Deterministic_downstream_lookup_record' in tools
    assert result.is_error is False
    assert result.structured_content == TOOL_RESULT
    assert journey.downstream.invocations == [{'record_id': 7}]

@pytest.mark.asyncio
async def test_downstream_failure_is_safe_and_public_http_session_remains_usable(runtime_resources: AsyncExitStack, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    journey = await _build_journey(tmp_path, monkeypatch, runtime_resources)
    journey.downstream.fail = True
    async with journey.app.router.lifespan_context(journey.app):
        journey.grant_permissions()
        async with Client(journey.transport()) as client:
            result = await client.call_tool('Deterministic_downstream_lookup_record', {'record_id': 7}, raise_on_error=False)
            tools_after_failure = {tool.name for tool in await client.list_tools()}
    assert result.is_error is True
    assert result.content[0].text == 'Tool invocation failed'
    assert SECRET_CANARY not in str(result)
    assert 'Deterministic_downstream_lookup_record' in tools_after_failure
    assert journey.downstream.invocations == [{'record_id': 7}]

@pytest.mark.parametrize('approved', [False, True], ids=['rejected', 'accepted'])
@pytest.mark.asyncio
async def test_admin_ask_policy_controls_downstream_http_invocation(runtime_resources: AsyncExitStack, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, approved: bool) -> None:
    journey = await _build_journey(tmp_path, monkeypatch, runtime_resources)
    policy = await journey.admin.put(f'/api/admin/connectors/mcp/{journey.connector_id}/tools/activation', json={'tools': [{'tool_id': TOOL_NAME, 'invocation_mode': 'ask', 'expected_policy_revision': 0}]})
    assert policy.status_code == 200

    async def approval_handler(message: str, *_args: object) -> dict[str, bool]:
        return {'value': approved}
    async with journey.app.router.lifespan_context(journey.app):
        journey.grant_permissions()
        async with Client(journey.transport(), elicitation_handler=approval_handler) as client:
            result = await client.call_tool('Deterministic_downstream_lookup_record', {'record_id': 7}, raise_on_error=False)
    assert result.is_error is not approved
    assert len(journey.downstream.invocations) == int(approved)
    if approved:
        assert result.structured_content == TOOL_RESULT
