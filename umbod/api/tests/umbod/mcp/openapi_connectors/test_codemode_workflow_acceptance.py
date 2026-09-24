from umbod.core.activation import CAPABILITY_ACTIVATION_STATE_TABLE
from umbod.core.connectors.openapi.stores import CATALOG_OPERATION_TABLE, CATALOG_SOURCE_TABLE, CONNECTOR_TABLE, CURRENT_CATALOG_HEADER_TABLE, OpenApiConnectorStoreService
from umbod.core.permissions.factories import create_group_permission_store
from umbod.infrastructure import ConfiguredPersistenceRuntimeProvider
from tests.persistence_runtime import prepared_sqlite_runtime
from tests.persistence_runtime import prepared_persistence_runtime
import json
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator
import httpx
import jwt
import pytest
from fastapi.testclient import TestClient
from fastmcp import Client, FastMCP
from fastmcp.server.auth.auth import AccessToken
from mcp.server.auth.middleware.auth_context import AuthenticatedUser, auth_context_var
from umbod.config import AppConfig, McpConfig
from umbod.core.capabilities import (
    UnrestrictedCapabilityActivation,
    UnrestrictedCapabilityPublication,
    UnrestrictedCapabilityReadiness,
)
from umbod.core.connectors.native.runtime import ConnectorRuntime
from umbod.core.connectors.native.runtime.tools import ConcreteConnectorToolMapping
from umbod.core.connectors.openapi.catalog import StoreBackedOpenApiCapabilityCatalog
from umbod.core.permissions import CapabilityPermissionCatalog, ConnectorPermissionUpdate, ConnectorToolRef, SaveGroupPermissionsRequest, ToolPermissionUpdate, UpdateGroupPermissionsRequest
from umbod.core.permissions.management import GroupPermissionManagementService
from umbod.mcp.auth import MCPAuthProviderFactory
from umbod.mcp.connectors import create_default_mcp_connector_runtime
from umbod.mcp.public_app import OpenApiRuntimeAdapters, build_mcp, build_mcp_with_openapi_adapters
from umbod.rest.main import create_app
from umbod.rest.settings import APISettings

class FakeStreamResponse:
    status_code = 200
    headers = httpx.Headers({'content-type': 'application/json', 'etag': 'safe-etag', 'x-secret': 'response-canary'})

    async def aiter_bytes(self) -> AsyncIterator[bytes]:
        yield json.dumps({'items': ['x' * 5000]}).encode()

@asynccontextmanager
async def _fake_stream_context() -> AsyncIterator[FakeStreamResponse]:
    yield FakeStreamResponse()

class RecordingOutboundHttpClient:

    def __init__(self) -> None:
        self.requests: list[tuple[str, str, dict[str, object]]] = []

    def stream(self, method: str, url: str, **kwargs: object) -> AbstractAsyncContextManager[FakeStreamResponse]:
        self.requests.append((method, url, kwargs))
        return _fake_stream_context()

    async def aclose(self) -> None:
        return None

class RecordingOutboundHttpClientFactory:

    def __init__(self) -> None:
        self.client = RecordingOutboundHttpClient()

    def create(self) -> RecordingOutboundHttpClient:
        return self.client

class NoopPermissionNotifier:

    def permissions_changed(self) -> bool:
        return False

def _document() -> dict[str, Any]:
    return {'openapi': '3.1.0', 'info': {'title': 'Inventory', 'version': '1'}, 'servers': [{'url': 'https://api.example.test'}], 'components': {'schemas': {'ItemUpdate': {'type': 'object', 'description': 'Fields used to update an inventory item.', 'properties': {'title': {'type': 'string', 'description': 'New inventory item title.', 'enum': ['Draft', 'Published']}, 'metadata': {'$ref': '#/components/schemas/ItemMetadata'}}, 'required': ['title'], 'additionalProperties': False}, 'ItemMetadata': {'type': 'object', 'properties': {'source': {'type': 'string', 'description': 'System that supplied the item.'}}, 'required': ['source'], 'additionalProperties': False}}}, 'paths': {'/items/{item_id}': {'get': {'operationId': 'getItem', 'summary': 'Get inventory item', 'parameters': [{'name': 'item_id', 'in': 'path', 'required': True, 'schema': {'type': 'string'}}, {'name': 'filter', 'in': 'query', 'schema': {'type': 'string'}}, {'name': 'X-Trace', 'in': 'header', 'schema': {'type': 'string'}}], 'requestBody': {'content': {'application/json': {'schema': {'$ref': '#/components/schemas/ItemUpdate'}}}}, 'responses': {'200': {'description': 'OK'}}}}}}

def _settings(database_path: Path, exposure_mode: str, token: str) -> AppConfig:
    return AppConfig(connector_store={'type': 'sqlite', 'sqlite_path': str(database_path)}, openapi_connectors={'json_import_max_bytes': 4096}, mcp=McpConfig(connector_tool_exposure_mode=exposure_mode, auth_mode='single_test_user', test_bearer_token=token, permission_group_claim='groups'), admin_authentication={'mode': 'simulation', 'simulated_admin': True})

def _unused_connector_operation() -> dict[str, object]:
    return {'unused': True}

async def _build(settings: AppConfig, factory: RecordingOutboundHttpClientFactory) -> FastMCP:
    persistence_runtime = ConfiguredPersistenceRuntimeProvider(settings.connector_store).create()
    await persistence_runtime.readiness.ensure_ready()
    default_runtime = await create_default_mcp_connector_runtime(settings, persistence_runtime)
    runtime = ConnectorRuntime(connector_registrations=({'id': 'acceptance', 'display_name': 'Acceptance', 'description': 'Acceptance boundary'},), connector_configuration_store=default_runtime.connector_configuration_store, connector_publishing_store=default_runtime.connector_publishing_store, connector_tool_mappings=(ConcreteConnectorToolMapping('acceptance', 'unused', 'Unused', _unused_connector_operation, {}),))
    return await build_mcp_with_openapi_adapters(settings, MCPAuthProviderFactory().create(settings), runtime, (), OpenApiRuntimeAdapters(factory), persistence_runtime)

async def _build_default(settings: AppConfig) -> FastMCP:
    persistence_runtime = ConfiguredPersistenceRuntimeProvider(settings.connector_store).create()
    await persistence_runtime.readiness.ensure_ready()
    default_runtime = await create_default_mcp_connector_runtime(settings, persistence_runtime)
    runtime = ConnectorRuntime(connector_registrations=({'id': 'acceptance', 'display_name': 'Acceptance', 'description': 'Acceptance boundary'},), connector_configuration_store=default_runtime.connector_configuration_store, connector_publishing_store=default_runtime.connector_publishing_store, connector_tool_mappings=(ConcreteConnectorToolMapping('acceptance', 'unused', 'Unused', _unused_connector_operation, {}),))
    return await build_mcp(settings, MCPAuthProviderFactory().create(settings), runtime, persistence_runtime)

async def _tool_names(mcp: FastMCP, token: str) -> set[str]:
    context_token = auth_context_var.set(AuthenticatedUser(_access_token(token)))
    try:
        async with Client(mcp) as client:
            return {tool.name for tool in await client.list_tools()}
    finally:
        auth_context_var.reset(context_token)

def _access_token(token: str) -> AccessToken:
    return AccessToken(token=token, client_id='engineer@example.test', scopes=[], claims=jwt.decode(token, options={'verify_signature': False}))

@pytest.fixture(autouse=True)
def connector_availability(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / 'connector-availability.json'
    path.write_text('{"connectors": []}', encoding='utf-8')
    monkeypatch.setenv('UMBOD_CONNECTOR_DEPLOYMENT_CONFIGURATION_PATH', str(path))

@pytest.mark.asyncio
async def test_admin_to_codemode_execution_enforces_live_sqlite_state(tmp_path: Path) -> None:
    database_path = tmp_path / 'shared.sqlite3'
    token = jwt.encode({'sub': 'engineer@example.test', 'email': 'engineer@example.test', 'groups': ['engineering']}, key='', algorithm='none')
    settings = _settings(database_path, 'codemode', token)
    admin = TestClient(create_app(settings=APISettings.model_validate(settings.model_dump()), connector_registrations=[]))
    connector_response = admin.post('/admin/connectors/openapi', json={'display_name': 'Inventory', 'capability_description': 'Manage inventory resources'})
    assert connector_response.status_code == 201
    connector_id = connector_response.json()['connector_id']
    imported = admin.post(f'/admin/connectors/openapi/{connector_id}/imports', json={'document': _document(), 'approved_hosts': ['api.example.test']})
    assert imported.status_code == 201
    assert admin.put(f'/admin/connectors/openapi/{connector_id}/publication').status_code == 200
    assert admin.put(f'/admin/connectors/openapi/{connector_id}/configuration', json={'bearer_token': 'runtime-token'}).status_code == 200
    activation_path = f'/admin/connectors/openapi/{connector_id}/tools/activation'
    enabled_activation = {'tools': [{'tool_id': 'getItem', 'activation_status': 'enabled'}]}
    disabled_activation = {'tools': [{'tool_id': 'getItem', 'activation_status': 'disabled'}]}
    assert admin.put(activation_path, json=enabled_activation).status_code == 200
    database = (await prepared_sqlite_runtime(database_path)).database
    permission_store = await create_group_permission_store(database)
    permissions = GroupPermissionManagementService(permission_store, CapabilityPermissionCatalog(StoreBackedOpenApiCapabilityCatalog(OpenApiConnectorStoreService((await prepared_persistence_runtime(AppConfig(connector_store={'type': 'sqlite', 'sqlite_path': str(database_path)}).connector_store)).database, CONNECTOR_TABLE, CURRENT_CATALOG_HEADER_TABLE, CATALOG_SOURCE_TABLE, CATALOG_OPERATION_TABLE, CAPABILITY_ACTIVATION_STATE_TABLE)), 'openapi', UnrestrictedCapabilityPublication(), UnrestrictedCapabilityActivation(), UnrestrictedCapabilityReadiness(), validate_connector_availability=False, validate_tool_availability=False, include_connector_without_tools=False), NoopPermissionNotifier())
    operation = ConnectorToolRef(connector_id, 'getItem')
    assert (await permissions.save_group_permissions(SaveGroupPermissionsRequest(group_id='engineering', connector_ids=(), capabilities=(operation.as_capability(),)))).status == 'applied'
    await prepared_sqlite_runtime(database_path)
    outbound_factory = RecordingOutboundHttpClientFactory()
    mcp = await _build(settings, outbound_factory)
    auth_context_var.set(AuthenticatedUser(_access_token(token)))
    async with Client(mcp) as client:
        tools = await client.list_tools()
        names = {tool.name for tool in tools}
        serialized_schemas = json.dumps([tool.input_schema for tool in tools]).lower()
        assert 'bearer_token' not in serialized_schemas
        assert 'authorization' not in serialized_schemas
        assert {'search_tools', 'execute_code'} <= names
        assert 'describe_openapi_capability' not in names
        assert 'execute_openapi_capability' not in names
        assert 'execute' not in names
        search_description = next((tool.description for tool in tools if tool.name == 'search_tools'))
        assert 'Inventory: Manage inventory resources (1 operations)' in search_description
        assert 'getItem' not in search_description
        assert 'item_id' not in search_description
        search = await client.call_tool('search_tools', {'query': 'inventory'})
        scoped_search = await client.call_tool('search_tools', {'query': 'inventory', 'connector_ids': ['unknown', connector_id]})
        denied_scoped_search = await client.call_tool('search_tools', {'query': 'inventory', 'connector_ids': ['unknown']})
        assert scoped_search.structured_content == search.structured_content
        assert denied_scoped_search.is_error is False
        assert denied_scoped_search.structured_content == {'matches': []}
        assert len(search.structured_content['matches']) == 1
        match = search.structured_content['matches'][0]
        assert match['tool_name'] == 'execute_openapi'
        assert match['connector_id'] == connector_id
        assert match['operation_name'] == 'getItem'
        input_schema = match['input_schema']
        assert input_schema['required'] == ['connector_id', 'operation_id', 'path', 'query', 'headers', 'body']
        assert input_schema['properties']['connector_id']['const'] == connector_id
        assert input_schema['properties']['operation_id']['const'] == 'getItem'
        assert set(input_schema['properties']['path']['properties']) == {'item_id'}
        assert input_schema['properties']['path']['required'] == ['item_id']
        assert set(input_schema['properties']['query']['properties']) == {'filter'}
        assert set(input_schema['properties']['headers']['properties']) == {'X-Trace'}
        body_schema = input_schema['properties']['body']
        assert 'oneOf' in body_schema
        body_value_schema = body_schema['oneOf'][1]['properties']['value']
        assert '$ref' not in json.dumps(body_value_schema)
        assert body_value_schema['description'] == 'Fields used to update an inventory item.'
        assert body_value_schema['required'] == ['title']
        assert body_value_schema['additionalProperties'] is False
        assert body_value_schema['properties']['title']['description'] == 'New inventory item title.'
        assert body_value_schema['properties']['title']['enum'] == ['Draft', 'Published']
        metadata_schema = body_value_schema['properties']['metadata']
        assert metadata_schema['required'] == ['source']
        assert metadata_schema['properties']['source']['description'] == 'System that supplied the item.'
        code = f'execute_openapi(connector_id="{connector_id}", operation_id="getItem", path={{"item_id": "safe-item"}}, query={{"filter": "raw-request-canary"}}, headers={{"X-Trace": "secret-canary"}}, body={{"state": "missing"}})'
        executed = await client.call_tool('execute_code', {'code': code})
        assert executed.structured_content['outcome'] == 'success'
        result = executed.structured_content['final_value']
        assert result == {'status': 'success', 'code': None, 'message': 'OpenAPI capability executed.', 'http_status': 200, 'content_type': 'application/json', 'response_size_bytes': 4096, 'truncated': True}
        assert outbound_factory.client.requests == [('GET', 'https://api.example.test/items/safe-item?filter=raw-request-canary', {'headers': {'x-trace': 'secret-canary', 'Authorization': 'Bearer runtime-token'}, 'timeout': settings.openapi_connectors.execution_read_timeout_seconds, 'follow_redirects': False})]
        assert admin.put(activation_path, json=disabled_activation).status_code == 200
        targets = admin.get('/admin/mcp-permissions/assignable-targets').json()
        assert (connector_id, 'getItem') not in {(item['connector_id'], item['capability_key']) for item in targets['capabilities']}
        unavailable_tools = await client.list_tools()
        unavailable_description = next((tool.description for tool in unavailable_tools if tool.name == 'search_tools'))
        assert 'Inventory (1)' not in unavailable_description
        unavailable_search = await client.call_tool('search_tools', {'query': 'inventory'})
        assert unavailable_search.structured_content['matches'] == []
        unavailable_execution = await client.call_tool('execute_code', {'code': code})
        assert unavailable_execution.structured_content['final_value']['code'] == 'capability_unavailable'
        assert len(outbound_factory.client.requests) == 1
        assert (await permissions.list_group_permissions('engineering')).tools == (operation,)
        assert admin.put(activation_path, json=enabled_activation).status_code == 200
        await permissions.update_group_permissions(UpdateGroupPermissionsRequest(group_id='engineering', connectors=(), capabilities=(ToolPermissionUpdate(operation, 'disabled').as_capability_update(),)))
        denied = await client.call_tool('execute_code', {'code': code})
        assert denied.structured_content['final_value']['code'] == 'capability_unavailable'
        assert len(outbound_factory.client.requests) == 1
        assert (await permissions.update_group_permissions(UpdateGroupPermissionsRequest(group_id='engineering', connectors=(ConnectorPermissionUpdate(connector_id, 'enabled'),), capabilities=()))).status == 'applied'
        connector_authorized = await client.call_tool('search_tools', {'query': 'inventory'})
        assert len(connector_authorized.structured_content['matches']) == 1
        assert admin.put(activation_path, json=disabled_activation).status_code == 200
        connector_disabled = await client.call_tool('search_tools', {'query': 'inventory'})
        assert connector_disabled.structured_content['matches'] == []
        disabled_execution = await client.call_tool('execute_code', {'code': code})
        assert disabled_execution.structured_content['final_value']['code'] == 'capability_unavailable'
        assert len(outbound_factory.client.requests) == 1
        assert admin.put(activation_path, json=enabled_activation).status_code == 200
        assert (await permissions.update_group_permissions(UpdateGroupPermissionsRequest(group_id='engineering', connectors=(ConnectorPermissionUpdate(connector_id, 'disabled'),), capabilities=()))).status == 'applied'
        revoked_tools = await client.list_tools()
        revoked_description = next((tool.description for tool in revoked_tools if tool.name == 'search_tools'))
        assert 'Inventory (1)' not in revoked_description
        revoked_search = await client.call_tool('search_tools', {'query': 'inventory'})
        assert revoked_search.structured_content['matches'] == []
        revoked_execution = await client.call_tool('execute_code', {'code': code})
        assert revoked_execution.structured_content['final_value']['code'] == 'capability_unavailable'
        assert len(outbound_factory.client.requests) == 1
    for mode in ('flat', 'gateway'):
        mode_names = await _tool_names(await _build_default(_settings(database_path, mode, token)), token)
        assert not {'search_openapi_capabilities', 'describe_openapi_capability', 'execute_openapi_capability'}.intersection(mode_names)
