from umbod.core.permissions.factories import create_group_permission_store
from umbod.infrastructure import ConfiguredPersistenceRuntimeProvider
from dataclasses import replace
from pathlib import Path
from typing import Any
import httpx2
import jwt
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from fastmcp import Client, FastMCP
from fastmcp.client.transports import StreamableHttpTransport
from fastmcp.tools import ToolResult
from starlette.applications import Starlette
from umbod.config import AppConfig, McpConfig
from umbod.core.connectors.downstream_mcp.probe import DiscoverDownstreamTools
from umbod.core.connectors.downstream_mcp.probe import DiscoveredCapabilities, DiscoveredCapabilityTool, ProbeCapabilities, ScriptedDownstreamMcpProbe
from umbod.core.permissions import ConnectorToolRef, SaveGroupPermissionsRequest
from umbod.mcp import public_app
from umbod.mcp.context import PublicAppRuntimeContext
from umbod.mcp.downstream_mcp_connectors.provider import UnrestrictedDownstreamToolPermissionPolicy
from umbod.rest.connectors.downstream_mcp.dependencies import get_downstream_connector_probe
from umbod.rest.main import create_app
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

    def __init__(self, app: Starlette, token: str, admin: TestClient, connector_id: str, downstream: DeterministicDownstream, context: PublicAppRuntimeContext) -> None:
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

def _settings(database_path: Path, token: str) -> AppConfig:
    return AppConfig(connector_store={'type': 'sqlite', 'sqlite_path': str(database_path)}, mcp=McpConfig(auth_mode='single_test_user', test_bearer_token=token, permission_group_claim='groups', connector_tool_exposure_mode='flat', downstream_discovery_enabled=False, stateless_http=True), endpoints={'mcp_base_url': 'http://localhost'}, admin_authentication={'mode': 'simulation', 'simulated_admin': True}, connector_security={'configuration_secret': 'integration-configuration-secret', 'approval_state_key': 'integration-approval-state-key-with-sufficient-entropy'})

async def _grant_permission(database_path: Path, connector_id: str) -> None:
    runtime = ConfiguredPersistenceRuntimeProvider(_settings(database_path, 'unused').connector_store).create()
    await runtime.readiness.ensure_ready()
    store = await create_group_permission_store(runtime.database)
    await store.save_group_permissions(SaveGroupPermissionsRequest(group_id='engineering', connector_ids=(connector_id,), capabilities=(ConnectorToolRef(connector_id, TOOL_NAME).as_capability(),)))

async def _build_journey(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> DownstreamHttpJourney:
    availability_path = tmp_path / 'connector-availability.json'
    availability_path.write_text('{"connectors": []}', encoding='utf-8')
    monkeypatch.setenv('UMBOD_CONNECTOR_DEPLOYMENT_CONFIGURATION_PATH', str(availability_path))
    database_path = tmp_path / 'shared-downstream-http.sqlite3'
    token = jwt.encode({'sub': 'engineer@example.test', 'email': 'engineer@example.test', 'groups': ['engineering']}, key='', algorithm='none')
    settings = _settings(database_path, token)
    capability = DiscoveredCapabilityTool(name=TOOL_NAME, title='Lookup record', description='Look up a deterministic record', input_schema={'type': 'object', 'properties': {'record_id': {'type': 'integer'}}, 'required': ['record_id']}, output_schema={'type': 'object'})
    probe = ScriptedDownstreamMcpProbe((ProbeCapabilities(capabilities=DiscoveredCapabilities(tools=(capability,)), endpoint_url='https://downstream.example.test/mcp'),))
    admin_app = create_app(settings=APISettings.model_validate(settings.model_dump()), connector_registrations=[])
    mounted_admin = next((route.app for route in admin_app.routes if route.path == '/admin'))
    assert isinstance(mounted_admin, FastAPI)
    mounted_admin.dependency_overrides[get_downstream_connector_probe] = lambda : probe
    admin = TestClient(admin_app)
    created = admin.post('/admin/connectors/mcp', json={'metadata': {'display_name': 'Deterministic downstream', 'capability_description': 'Look up records', 'public_path': '/mcp/proxies/deterministic-downstream'}, 'configuration': {'endpoint_url': 'https://downstream.example.test/mcp', 'auth_mode': 'none'}})
    assert created.status_code == 201
    connector_id = created.json()['connector_id']
    published = admin.put(f'/admin/connectors/mcp/{connector_id}/publication')
    enabled = admin.put(f'/admin/connectors/mcp/{connector_id}/tools/activation', json={'tools': [{'tool_id': TOOL_NAME, 'activation_status': 'enabled'}]})
    assert published.status_code == 200
    assert enabled.status_code == 200
    await _grant_permission(database_path, connector_id)
    downstream = DeterministicDownstream()
    monkeypatch.setattr('umbod.core.connectors.downstream_mcp.adapters.fastmcp.client.FastMCPDownstreamClientFactory.create', downstream.create)
    config = await public_app.load_configured_public_app_config(settings)
    context = await public_app.create_runtime_context(config)
    context = replace(context, api_base_url=None)
    context.mcp.downstream_mcp_tool_provider._permission_policy = UnrestrictedDownstreamToolPermissionPolicy()
    return DownstreamHttpJourney(await public_app.build_starlette_app(context), token, admin, connector_id, downstream, context)

@pytest.mark.asyncio
async def test_admin_registered_downstream_tool_roundtrips_through_public_mcp_http(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    journey = await _build_journey(tmp_path, monkeypatch)
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
async def test_downstream_failure_is_safe_and_public_http_session_remains_usable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    journey = await _build_journey(tmp_path, monkeypatch)
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
async def test_admin_ask_policy_controls_downstream_http_invocation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, approved: bool) -> None:
    journey = await _build_journey(tmp_path, monkeypatch)
    policy = journey.admin.put(f'/admin/connectors/mcp/{journey.connector_id}/tools/activation', json={'tools': [{'tool_id': TOOL_NAME, 'invocation_mode': 'ask', 'expected_policy_revision': 0}]})
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
