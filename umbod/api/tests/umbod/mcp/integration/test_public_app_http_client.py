from umbod.core.publishing.stores.schema import PUBLICATION_STATE_TABLE
from umbod.core.publishing.stores.service import ConnectorPublishingStoreService
from umbod.infrastructure import ConfiguredPersistenceRuntimeProvider
from tests.persistence_runtime import create_inmemory_runtime
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any, Literal, Optional
import httpx2
import jwt
import pytest
from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport
from fastapi.testclient import TestClient
from fastmcp.exceptions import ToolError
from mcp.shared.exceptions import MCPError
from pydantic import ConfigDict, Field, SecretStr
from starlette.applications import Starlette
from umbod.config import ConnectorStoreConfig
from umbod.core.configuration import InMemoryConnectorCurrentConfigurationStore
from umbod.core.connectors.native.deployment.availability import DeploymentConnectorAvailability
from umbod.core.connectors.native.runtime import assemble_connector_runtime
from umbod.core.activation import (
    ActivationStatus,
    CapabilityRef,
    create_capability_activation_store,
)
from umbod.core.capabilities.tools.refs import ConnectorToolRef
from umbod.core.connectors.native.tools.runtime_state import ConnectorToolRuntimeState
from umbod.mcp.connectors.tools import ConnectorToolRuntimeStateSynchronizer, InMemoryConnectorToolRuntimeStateStore
from umbod.mcp.context import PublicAppConfig, PublicAppRuntimeContext
from umbod.mcp.public_app import build_starlette_app, create_runtime_context
from umbod.mcp.runtime_options import ConnectorRuntimeSourceStores, LocalConnectorRuntimeStateSourceStrategy
from umbod.mcp.settings import MCPAppSettings, MCPSettings
from umbod.rest.main import create_app
from umbod.rest.settings import APISettings
from umbod_sdk.connectors.plugin_api import ConfigurationCheckResult, Connector
from umbod_sdk.connectors.proxies import Model

class EchoConfiguration(Model):
    model_config = ConfigDict(extra='forbid')
    api_token: SecretStr = Field(description='Token used by the echo connector.')

def _echo_connector() -> Connector:
    connector = Connector(id='echo', name='Echo', description='Returns messages to MCP clients.', capability_description='Echo deterministic messages.', configuration=EchoConfiguration)

    @connector.configuration_check
    def check_configuration(configuration: EchoConfiguration) -> ConfigurationCheckResult:
        return ConfigurationCheckResult.valid()

    @connector.tool(description='Return a message to the caller.')
    def echo_message(message: str=Field(description='Message to return.'), configuration: Optional[EchoConfiguration]=None) -> dict[str, str]:
        return {'message': message}

    @connector.prompt(description='Create a prompt that asks an agent to repeat a message.')
    def repeat_message(message: str=Field(description='Message for the agent to repeat.'), configuration: Optional[EchoConfiguration]=None) -> str:
        return f'Repeat this message exactly: {message}'

    @connector.resource('echo://messages/{message}', name='echo_message', description='Read a deterministic echo message.')
    def read_message(message: str=Field(description='Message to read.'), configuration: Optional[EchoConfiguration]=None) -> str:
        return f'Echo resource: {message}'
    return connector

async def _build_public_app(tmp_path: Path, exposure_mode: Literal['flat', 'gateway', 'codemode']='flat') -> tuple[Starlette, str, PublicAppRuntimeContext, ConnectorPublishingStoreService]:
    token = jwt.encode({'email': 'agent@example.com', 'groups': ['agents']}, key='', algorithm='none')
    settings = MCPAppSettings(mcp=MCPSettings(auth_mode='single_test_user', test_bearer_token=token, connector_tool_exposure_mode=exposure_mode, downstream_discovery_enabled=False, stateless_http=True, _env_file=None), endpoints={'mcp_base_url': 'http://localhost'}, connector_store=ConnectorStoreConfig(type='sqlite', sqlite_path=str(tmp_path / 'agent-http-integration.sqlite3')), connector_security={'configuration_secret': 'test-secret', 'approval_state_key': 'integration-approval-state-key-with-sufficient-entropy'}, _env_file=None)
    configuration_store = InMemoryConnectorCurrentConfigurationStore()
    publishing_store = ConnectorPublishingStoreService(create_inmemory_runtime().database, PUBLICATION_STATE_TABLE)
    await configuration_store.save_current_configuration('echo', EchoConfiguration(api_token=SecretStr('valid-token')))
    await publishing_store.publish_connector('echo')
    connector_runtime = assemble_connector_runtime(plugins=[_echo_connector()], availability=DeploymentConnectorAvailability.from_mapping({'connectors': [{'id': 'echo'}]}), configuration_store=configuration_store, publishing_store=publishing_store)
    tool_state_store = InMemoryConnectorToolRuntimeStateStore()
    tool_state_store.save_runtime_state(ConnectorToolRuntimeState(key=ConnectorToolRef('echo', 'echo_message'), status='enabled'))
    persistence_runtime = ConfiguredPersistenceRuntimeProvider(settings.connector_store).create()
    await persistence_runtime.readiness.ensure_ready()
    activation_store = await create_capability_activation_store(persistence_runtime.database)
    await activation_store.set_status(
        CapabilityRef('native', 'echo', 'prompt', 'repeat_message'),
        ActivationStatus.ENABLED,
    )
    await activation_store.set_status(
        CapabilityRef(
            'native', 'echo', 'resource_template', 'echo://messages/{message}'
        ),
        ActivationStatus.ENABLED,
    )
    context = await create_runtime_context(PublicAppConfig(settings=settings, connector_runtime=connector_runtime, source_stores=ConnectorRuntimeSourceStores(), configured_source_strategy=LocalConnectorRuntimeStateSourceStrategy(configuration_store, publishing_store), stateless_http=True, api_base_url=None, persistence_runtime=persistence_runtime, connector_tool_runtime_state_store=tool_state_store))
    context.group_permission_runtime_state.grant_connector('agents', 'echo')
    context.group_permission_runtime_state.grant_tool('agents', 'echo', 'echo_message')
    context.group_permission_runtime_state.grant_capability(
        'agents', 'echo', 'prompt', 'repeat_message'
    )
    context.group_permission_runtime_state.grant_capability(
        'agents', 'echo', 'resource_template', 'echo://messages/{message}'
    )
    return (await build_starlette_app(context), token, context, publishing_store)

class _RestConnectorToolRuntimeStateReader:

    def __init__(self, admin: TestClient) -> None:
        self._admin = admin

    async def get_runtime_state(self, key: ConnectorToolRef) -> Optional[ConnectorToolRuntimeState]:
        response = self._admin.get(f'/system/connectors/{key.connector_id}/tool/{key.operation_name}')
        if response.status_code == 404:
            return None
        response.raise_for_status()
        status = response.json()['status']
        if status not in ('enabled', 'disabled'):
            raise ValueError(f'Unexpected connector tool status: {status}')
        return ConnectorToolRuntimeState(key=key, status=status)

async def _synchronize_echo_tool_runtime_state(admin: TestClient, context: PublicAppRuntimeContext) -> None:
    synchronizer = ConnectorToolRuntimeStateSynchronizer(reader=_RestConnectorToolRuntimeStateReader(admin), store=context.connector_tool_runtime_state_store, reconciler=context.mcp.connector_tool_registry)
    await synchronizer.sync_runtime_state(ConnectorToolRef('echo', 'echo_message'))

def _http_transport(app: Starlette, token: Optional[str], request_hook: Optional[Callable[[httpx2.Request], Awaitable[None]]]=None) -> StreamableHttpTransport:
    asgi_transport = httpx2.ASGITransport(app=app)

    def create_http_client(**kwargs: Any) -> httpx2.AsyncClient:
        event_hooks = {'request': [request_hook]} if request_hook is not None else None
        return httpx2.AsyncClient(transport=asgi_transport, event_hooks=event_hooks, **kwargs)
    headers = {'Authorization': f'Bearer {token}'} if token is not None else None
    return StreamableHttpTransport('http://localhost/mcp', headers=headers, httpx_client_factory=create_http_client)

@pytest.mark.asyncio
async def test_authenticated_agent_discovers_and_invokes_published_tool_over_http(tmp_path: Path) -> None:
    (app, token, _context, _publishing_store) = await _build_public_app(tmp_path)
    async with app.router.lifespan_context(app):
        async with Client(_http_transport(app, token)) as client:
            tools = {tool.name: tool for tool in await client.list_tools()}
            result = await client.call_tool('echo_echo_message', {'message': 'hello from an agent'})
    assert 'echo_echo_message' in tools
    assert tools['echo_echo_message'].input_schema['required'] == ['message']
    assert result.is_error is False
    assert result.structured_content == {'message': 'hello from an agent'}

@pytest.mark.parametrize('presented_token', [None, 'invalid-token'], ids=['missing', 'invalid'])
@pytest.mark.asyncio
async def test_agent_without_valid_authentication_is_rejected_during_http_initialization(tmp_path: Path, presented_token: Optional[str]) -> None:
    (app, _token, _context, _publishing_store) = await _build_public_app(tmp_path)
    with pytest.raises(ExceptionGroup) as rejection:
        async with app.router.lifespan_context(app):
            async with Client(_http_transport(app, presented_token)):
                pass
    assert len(rejection.value.exceptions) == 1
    error = rejection.value.exceptions[0]
    assert isinstance(error, MCPError)
    assert error.code == -32603
    assert error.message == 'Server returned an error response'

@pytest.mark.asyncio
async def test_development_mode_handles_sequential_requests_without_session_id(tmp_path: Path) -> None:
    (app, token, _context, _publishing_store) = await _build_public_app(tmp_path)
    observed_session_ids: list[Optional[str]] = []

    async def record_session_id(request: httpx2.Request) -> None:
        observed_session_ids.append(request.headers.get('mcp-session-id'))
    transport = _http_transport(app, token, record_session_id)
    async with app.router.lifespan_context(app):
        async with Client(transport) as client:
            await client.list_tools()
            session_id = transport.get_session_id()
            result = await client.call_tool('echo_echo_message', {'message': 'stateless'})
    assert session_id is None
    assert observed_session_ids
    assert set(observed_session_ids) == {None}
    assert result.is_error is False
    assert result.structured_content == {'message': 'stateless'}

@pytest.mark.parametrize('exposure_mode', ['flat', 'gateway', 'codemode'])
@pytest.mark.asyncio
async def test_authenticated_agent_discovers_and_invokes_tool_in_exposure_mode(tmp_path: Path, exposure_mode: Literal['flat', 'gateway', 'codemode']) -> None:
    (app, token, _context, _publishing_store) = await _build_public_app(tmp_path, exposure_mode)
    async with app.router.lifespan_context(app):
        async with Client(_http_transport(app, token)) as client:
            tool_names = {tool.name for tool in await client.list_tools()}
            if exposure_mode == 'flat':
                result = await client.call_tool('echo_echo_message', {'message': exposure_mode})
            elif exposure_mode == 'gateway':
                search = await client.call_tool('search_tools', {'query': 'echo message'})
                result = await client.call_tool('execute_tool', {'tool_name': 'echo_echo_message', 'arguments': {'message': exposure_mode}})
            else:
                search = await client.call_tool('search_tools', {'query': 'echo message'})
                result = await client.call_tool('execute_code', {'code': 'echo_echo_message(message="codemode")'})
    if exposure_mode == 'flat':
        assert 'echo_echo_message' in tool_names
        assert 'search_tools' not in tool_names
        assert result.structured_content == {'message': 'flat'}
    else:
        assert 'echo_echo_message' not in tool_names
        assert 'search_tools' in tool_names
        assert search.structured_content['matches'][0]['tool_name'] == 'echo_echo_message'
        if exposure_mode == 'gateway':
            assert 'execute_tool' in tool_names
            assert result.structured_content == {'message': 'gateway'}
        else:
            assert 'execute_code' in tool_names
            assert result.structured_content['outcome'] == 'success'
            assert result.structured_content['final_value'] == {'message': 'codemode'}

@pytest.mark.asyncio
async def test_agent_receives_validation_error_for_missing_required_tool_argument(tmp_path: Path) -> None:
    (app, token, _context, _publishing_store) = await _build_public_app(tmp_path)
    async with app.router.lifespan_context(app):
        async with Client(_http_transport(app, token)) as client:
            with pytest.raises(ToolError) as rejection:
                await client.call_tool('echo_echo_message', {})
    assert 'message' in str(rejection.value)
    assert 'Missing required argument' in str(rejection.value)

@pytest.mark.asyncio
async def test_agent_cannot_distinguish_unknown_tool_from_unauthorized_tool(tmp_path: Path) -> None:
    (app, token, _context, _publishing_store) = await _build_public_app(tmp_path)
    async with app.router.lifespan_context(app):
        async with Client(_http_transport(app, token)) as client:
            with pytest.raises(ToolError) as rejection:
                await client.call_tool('unknown_tool', {})
    assert str(rejection.value) == "Authorization failed for tool 'unknown_tool': not found or not authorized"

@pytest.mark.asyncio
async def test_admin_activation_changes_public_tool_discovery_and_stale_invocation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    availability_path = tmp_path / 'connector-availability.json'
    availability_path.write_text('{"connectors": [{"id": "echo"}]}', encoding='utf-8')
    monkeypatch.setenv('UMBOD_CONNECTOR_DEPLOYMENT_CONFIGURATION_PATH', str(availability_path))
    (app, token, context, _publishing_store) = await _build_public_app(tmp_path)
    admin = TestClient(create_app(settings=APISettings.model_validate(context.settings.model_dump()), connector_registrations=[_echo_connector().registration()]))
    activation_path = '/admin/connectors/catalog/echo/tools/activation'
    async with app.router.lifespan_context(app):
        async with Client(_http_transport(app, token)) as client:
            enabled_response = admin.put(activation_path, json={'tools': [{'tool_id': 'echo_message', 'activation_status': 'enabled'}]})
            await _synchronize_echo_tool_runtime_state(admin, context)
            names_when_enabled = {tool.name for tool in await client.list_tools()}
            disabled_response = admin.put(activation_path, json={'tools': [{'tool_id': 'echo_message', 'activation_status': 'disabled'}]})
            await _synchronize_echo_tool_runtime_state(admin, context)
            names_when_disabled = {tool.name for tool in await client.list_tools()}
            with pytest.raises(ToolError) as rejection:
                await client.call_tool('echo_echo_message', {'message': 'stale'})
    assert enabled_response.status_code == 200
    assert enabled_response.json()['tools'][0]['activation_status'] == 'enabled'
    assert 'echo_echo_message' in names_when_enabled
    assert disabled_response.status_code == 200
    assert disabled_response.json()['tools'][0]['activation_status'] == 'disabled'
    assert 'echo_echo_message' not in names_when_disabled
    assert str(rejection.value) == "Authorization failed for tool 'echo_echo_message': not found or not authorized"

@pytest.mark.parametrize('approved', [True, False], ids=['accepted', 'rejected'])
@pytest.mark.asyncio
async def test_admin_ask_policy_requires_agent_confirmation_before_http_invocation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, approved: bool) -> None:
    availability_path = tmp_path / 'connector-availability.json'
    availability_path.write_text('{"connectors": [{"id": "echo"}]}', encoding='utf-8')
    monkeypatch.setenv('UMBOD_CONNECTOR_DEPLOYMENT_CONFIGURATION_PATH', str(availability_path))
    (app, token, context, _publishing_store) = await _build_public_app(tmp_path)
    admin = TestClient(create_app(settings=APISettings.model_validate(context.settings.model_dump()), connector_registrations=[_echo_connector().registration()]))
    policy_response = admin.put('/admin/connectors/catalog/echo/tools/activation', json={'tools': [{'tool_id': 'echo_message', 'invocation_mode': 'ask', 'expected_policy_revision': 0}]})
    approval_requests: list[str] = []

    async def confirmation_handler(message: str, *_args: object) -> dict[str, bool]:
        approval_requests.append(message)
        return {'value': approved}
    async with app.router.lifespan_context(app):
        async with Client(_http_transport(app, token), elicitation_handler=confirmation_handler) as client:
            result = await client.call_tool('echo_echo_message', {'message': 'requires approval'}, raise_on_error=False)
    assert policy_response.status_code == 200
    assert policy_response.json()['tools'][0]['invocation_mode'] == 'ask'
    assert len(approval_requests) == 1
    assert 'echo_echo_message' in approval_requests[0]
    assert result.is_error is not approved
    if approved:
        assert result.structured_content == {'message': 'requires approval'}

@pytest.mark.asyncio
async def test_admin_changes_observed_ask_policy_to_direct_without_further_elicitation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    availability_path = tmp_path / 'connector-availability.json'
    availability_path.write_text('{"connectors": [{"id": "echo"}]}', encoding='utf-8')
    monkeypatch.setenv('UMBOD_CONNECTOR_DEPLOYMENT_CONFIGURATION_PATH', str(availability_path))
    (app, token, context, _publishing_store) = await _build_public_app(tmp_path)
    admin = TestClient(create_app(settings=APISettings.model_validate(context.settings.model_dump()), connector_registrations=[_echo_connector().registration()]))
    activation_path = '/admin/connectors/catalog/echo/tools/activation'
    ask_response = admin.put(activation_path, json={'tools': [{'tool_id': 'echo_message', 'invocation_mode': 'ask', 'expected_policy_revision': 0}]})
    approval_requests: list[str] = []

    async def confirmation_handler(message: str, *_args: object) -> dict[str, bool]:
        approval_requests.append(message)
        return {'value': True}
    async with app.router.lifespan_context(app):
        async with Client(_http_transport(app, token), elicitation_handler=confirmation_handler) as client:
            ask_result = await client.call_tool('echo_echo_message', {'message': 'ask first'})
            direct_response = admin.put(activation_path, json={'tools': [{'tool_id': 'echo_message', 'invocation_mode': 'direct', 'expected_policy_revision': 1}]})
            direct_result = await client.call_tool('echo_echo_message', {'message': 'direct next'})
    assert ask_response.status_code == 200
    assert ask_response.json()['tools'][0]['policy_revision'] == 1
    assert ask_result.structured_content == {'message': 'ask first'}
    assert len(approval_requests) == 1
    assert direct_response.status_code == 200
    assert direct_response.json()['tools'][0]['invocation_mode'] == 'direct'
    assert direct_response.json()['tools'][0]['policy_revision'] == 2
    assert direct_result.is_error is False
    assert direct_result.structured_content == {'message': 'direct next'}

@pytest.mark.asyncio
async def test_authenticated_agent_discovers_and_uses_prompt_and_resource_over_http(tmp_path: Path) -> None:
    (app, token, _context, _publishing_store) = await _build_public_app(tmp_path)
    async with app.router.lifespan_context(app):
        async with Client(_http_transport(app, token)) as client:
            prompts = {prompt.name: prompt for prompt in await client.list_prompts()}
            prompt = await client.get_prompt('echo_repeat_message', {'message': 'hello'})
            templates = {template.uri_template: template for template in await client.list_resource_templates()}
            resources = await client.read_resource('echo://messages/hello')
    assert 'echo_repeat_message' in prompts
    assert prompts['echo_repeat_message'].arguments is not None
    assert prompts['echo_repeat_message'].arguments[0].name == 'message'
    assert prompt.messages[0].content.text == 'Repeat this message exactly: hello'
    assert 'echo://messages/{message}' in templates
    assert templates['echo://messages/{message}'].name == 'echo_message'
    assert resources[0].text == 'Echo resource: hello'

@pytest.mark.asyncio
async def test_agent_loses_discovery_and_execution_when_connector_is_unpublished(tmp_path: Path) -> None:
    (app, token, _context, publishing_store) = await _build_public_app(tmp_path)
    async with app.router.lifespan_context(app):
        async with Client(_http_transport(app, token)) as client:
            names_before = {tool.name for tool in await client.list_tools()}
            await publishing_store.unpublish_connector('echo')
            names_after = {tool.name for tool in await client.list_tools()}
            with pytest.raises(ToolError) as rejection:
                await client.call_tool('echo_echo_message', {'message': 'stale'})
    assert 'echo_echo_message' in names_before
    assert 'echo_echo_message' not in names_after
    assert str(rejection.value) == "Authorization failed for tool 'echo_echo_message': not found or not authorized"

@pytest.mark.asyncio
async def test_agent_loses_discovery_and_execution_when_permission_is_revoked(tmp_path: Path) -> None:
    (app, token, context, _publishing_store) = await _build_public_app(tmp_path)
    async with app.router.lifespan_context(app):
        async with Client(_http_transport(app, token)) as client:
            names_before = {tool.name for tool in await client.list_tools()}
            context.group_permission_runtime_state.replace_group_permissions({}, {})
            names_after = {tool.name for tool in await client.list_tools()}
            with pytest.raises(ToolError) as rejection:
                await client.call_tool('echo_echo_message', {'message': 'stale'})
    assert 'echo_echo_message' in names_before
    assert 'echo_echo_message' not in names_after
    assert str(rejection.value) == "Authorization failed for tool 'echo_echo_message': insufficient permissions"
