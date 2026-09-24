from umbod.core.activation import CAPABILITY_ACTIVATION_STATE_TABLE
from umbod.core.connectors.openapi.stores import CATALOG_OPERATION_TABLE, CATALOG_SOURCE_TABLE, CONNECTOR_TABLE, CURRENT_CATALOG_HEADER_TABLE, OpenApiConnectorStoreService
from umbod.core.permissions.factories import create_group_permission_store
from umbod.infrastructure import ConfiguredPersistenceRuntimeProvider
import json
from collections.abc import AsyncIterator
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from dataclasses import replace
from pathlib import Path
from typing import Any
import httpx
import httpx2
import jwt
import pytest
from fastapi.testclient import TestClient
from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport
from starlette.applications import Starlette
from umbod.config import AppConfig, McpConfig
from umbod.core.capabilities import (
    UnrestrictedCapabilityActivation,
    UnrestrictedCapabilityPublication,
    UnrestrictedCapabilityReadiness,
)
from umbod.core.connectors.openapi.catalog import StoreBackedOpenApiCapabilityCatalog
from umbod.core.permissions import CapabilityPermissionCatalog, ConnectorToolRef, SaveGroupPermissionsRequest
from umbod.core.permissions.management import GroupPermissionManagementService
from umbod.mcp import public_app
from umbod.mcp.public_app import OpenApiRuntimeAdapters
from umbod.rest.main import create_app
from umbod.rest.settings import APISettings

class RecordingResponse:
    status_code = 200
    headers = httpx.Headers({'content-type': 'application/json', 'x-outbound-secret': 'response-secret'})

    async def aiter_bytes(self) -> AsyncIterator[bytes]:
        yield json.dumps({'inventory': 'available', 'secret': 'response-secret'}).encode()

@asynccontextmanager
async def _response_context() -> AsyncIterator[RecordingResponse]:
    yield RecordingResponse()

class RecordingOutboundHttpClient:

    def __init__(self) -> None:
        self.requests: list[tuple[str, str, dict[str, object]]] = []

    def stream(self, method: str, url: str, **kwargs: object) -> AbstractAsyncContextManager[RecordingResponse]:
        self.requests.append((method, url, kwargs))
        return _response_context()

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

def _settings(database_path: Path, token: str) -> AppConfig:
    return AppConfig(connector_store={'type': 'sqlite', 'sqlite_path': str(database_path)}, openapi_connectors={'json_import_max_bytes': 4096}, mcp=McpConfig(auth_mode='single_test_user', test_bearer_token=token, permission_group_claim='groups', connector_tool_exposure_mode='codemode', downstream_discovery_enabled=False, stateless_http=True), endpoints={'mcp_base_url': 'http://localhost'}, admin_authentication={'mode': 'simulation', 'simulated_admin': True}, connector_security={'configuration_secret': 'integration-configuration-secret', 'approval_state_key': 'integration-approval-state-key-with-sufficient-entropy'})

def _document() -> dict[str, Any]:
    return {'openapi': '3.1.0', 'info': {'title': 'Inventory', 'version': '1'}, 'servers': [{'url': 'https://inventory.example.test'}], 'paths': {'/items/{item_id}': {'get': {'operationId': 'getItem', 'summary': 'Get an inventory item', 'parameters': [{'name': 'item_id', 'in': 'path', 'required': True, 'schema': {'type': 'string'}}, {'name': 'expand', 'in': 'query', 'schema': {'type': 'string'}}, {'name': 'X-Trace', 'in': 'header', 'schema': {'type': 'string'}}], 'responses': {'200': {'description': 'OK'}}}}}}

def _http_transport(app: Starlette, token: str) -> StreamableHttpTransport:
    asgi_transport = httpx2.ASGITransport(app=app)

    def create_http_client(**kwargs: Any) -> httpx2.AsyncClient:
        return httpx2.AsyncClient(transport=asgi_transport, **kwargs)
    return StreamableHttpTransport('http://localhost/mcp', headers={'Authorization': f'Bearer {token}'}, httpx_client_factory=create_http_client)

async def _grant_permission(database_path: Path, connector_id: str) -> None:
    connector_store = AppConfig(connector_store={'type': 'sqlite', 'sqlite_path': str(database_path)}).connector_store
    persistence_runtime = ConfiguredPersistenceRuntimeProvider(connector_store).create()
    await persistence_runtime.readiness.ensure_ready()
    permission_store = await create_group_permission_store(persistence_runtime.database)
    permissions = GroupPermissionManagementService(permission_store, CapabilityPermissionCatalog(StoreBackedOpenApiCapabilityCatalog(OpenApiConnectorStoreService(persistence_runtime.database, CONNECTOR_TABLE, CURRENT_CATALOG_HEADER_TABLE, CATALOG_SOURCE_TABLE, CATALOG_OPERATION_TABLE, CAPABILITY_ACTIVATION_STATE_TABLE)), 'openapi', UnrestrictedCapabilityPublication(), UnrestrictedCapabilityActivation(), UnrestrictedCapabilityReadiness(), validate_connector_availability=False, validate_tool_availability=False, include_connector_without_tools=False), NoopPermissionNotifier())
    result = await permissions.save_group_permissions(SaveGroupPermissionsRequest(group_id='engineering', connector_ids=(), capabilities=(ConnectorToolRef(connector_id, 'getItem').as_capability(),)))
    assert result.status == 'applied'

@pytest.mark.asyncio
async def test_admin_openapi_connector_roundtrips_through_public_mcp_http(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    availability_path = tmp_path / 'connector-availability.json'
    availability_path.write_text('{"connectors": []}', encoding='utf-8')
    monkeypatch.setenv('UMBOD_CONNECTOR_DEPLOYMENT_CONFIGURATION_PATH', str(availability_path))
    database_path = tmp_path / 'shared-openapi-http.sqlite3'
    bearer_secret = 'runtime-bearer-secret'
    token = jwt.encode({'sub': 'engineer@example.test', 'email': 'engineer@example.test', 'groups': ['engineering']}, key='', algorithm='none')
    settings = _settings(database_path, token)
    admin = TestClient(create_app(settings=APISettings.model_validate(settings.model_dump()), connector_registrations=[]))
    created = admin.post('/admin/connectors/openapi', json={'display_name': 'Inventory', 'capability_description': 'Read inventory'})
    assert created.status_code == 201
    connector_id = created.json()['connector_id']
    imported = admin.post(f'/admin/connectors/openapi/{connector_id}/imports', json={'document': _document(), 'approved_hosts': ['inventory.example.test']})
    configured = admin.put(f'/admin/connectors/openapi/{connector_id}/configuration', json={'bearer_token': bearer_secret})
    published = admin.put(f'/admin/connectors/openapi/{connector_id}/publication')
    activation_path = f'/admin/connectors/openapi/{connector_id}/tools/activation'
    enabled = admin.put(activation_path, json={'tools': [{'tool_id': 'getItem', 'activation_status': 'enabled'}]})
    assert imported.status_code == 201
    assert configured.status_code == 200
    assert published.status_code == 200
    assert enabled.status_code == 200
    await _grant_permission(database_path, connector_id)
    outbound_factory = RecordingOutboundHttpClientFactory()
    monkeypatch.setattr(public_app, '_default_openapi_runtime_adapters', lambda _settings: OpenApiRuntimeAdapters(outbound_factory))
    config = await public_app.load_configured_public_app_config(settings)
    context = await public_app.create_runtime_context(config)
    context = replace(context, api_base_url=None)
    context.group_permission_runtime_state.grant_tool('engineering', connector_id, 'getItem')
    app = await public_app.build_starlette_app(context)
    code = f'execute_openapi(connector_id="{connector_id}", operation_id="getItem", path={{"item_id": "item-7"}}, query={{"expand": "supplier"}}, headers={{"X-Trace": "trace-9"}}, body={{"state": "missing"}})'
    async with app.router.lifespan_context(app):
        async with Client(_http_transport(app, token)) as client:
            tools = await client.list_tools()
            search = await client.call_tool('search_tools', {'query': 'inventory'})
            executed = await client.call_tool('execute_code', {'code': code})
            disabled = admin.put(activation_path, json={'tools': [{'tool_id': 'getItem', 'activation_status': 'disabled'}]})
            unavailable_search = await client.call_tool('search_tools', {'query': 'inventory'})
            stale = await client.call_tool('execute_code', {'code': code})
    assert {tool.name for tool in tools} >= {'search_tools', 'execute_code'}
    serialized_tools = json.dumps([tool.input_schema for tool in tools]).lower()
    assert bearer_secret not in serialized_tools
    assert 'bearer_token' not in serialized_tools
    assert search.structured_content['matches'][0]['operation_name'] == 'getItem'
    assert executed.structured_content['outcome'] == 'success'
    assert executed.structured_content['final_value'] == {'status': 'success', 'code': None, 'message': 'OpenAPI capability executed.', 'http_status': 200, 'content_type': 'application/json', 'response_size_bytes': 55, 'truncated': False}
    assert bearer_secret not in json.dumps(executed.structured_content)
    assert 'response-secret' not in json.dumps(executed.structured_content)
    assert outbound_factory.client.requests == [('GET', 'https://inventory.example.test/items/item-7?expand=supplier', {'headers': {'x-trace': 'trace-9', 'Authorization': f'Bearer {bearer_secret}'}, 'timeout': settings.openapi_connectors.execution_read_timeout_seconds, 'follow_redirects': False})]
    assert disabled.status_code == 200
    assert unavailable_search.structured_content == {'matches': []}
    assert stale.structured_content['final_value']['code'] == 'capability_unavailable'
    assert len(outbound_factory.client.requests) == 1
