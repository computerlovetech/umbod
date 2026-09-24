from umbod.core.connectors.downstream_mcp.stores import TOOL_CATALOG_TABLE, ToolCatalogStoreService
from tests.persistence_runtime import create_sqlite_runtime
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast
from uuid import UUID
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from umbod.core.connectors.downstream_mcp.models import DiscoveredServerIcon, DiscoveredToolWithoutOutputSchema, ToolCatalogSnapshot, ToolIdentity
from umbod.core.connectors.downstream_mcp.stores import ReplaceToolCatalog
from umbod.core.connectors.downstream_mcp.probe import DiscoveredCapabilities, DownstreamConnectorValidationFailed, DownstreamConnectorValidationResult, DownstreamConnectorValidationSucceeded, ProbeCapabilities, ProbeFailed, ScriptedDownstreamMcpProbe
from umbod.rest.connectors.downstream_mcp.dependencies import get_downstream_connector_probe
from umbod.rest.main import create_app
from umbod.rest.settings import APISettings

@pytest.fixture(autouse=True)
def connector_availability(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / 'connector-availability.json'
    path.write_text('{"connectors": []}', encoding='utf-8')
    monkeypatch.setenv('UMBOD_CONNECTOR_DEPLOYMENT_CONFIGURATION_PATH', str(path))

def _probe(results: Sequence[DownstreamConnectorValidationResult], canonical_endpoint_url: str) -> ScriptedDownstreamMcpProbe:
    return ScriptedDownstreamMcpProbe(tuple((ProbeFailed(code=result.code) if isinstance(result, DownstreamConnectorValidationFailed) else ProbeCapabilities(capabilities=DiscoveredCapabilities(tools=()), endpoint_url=canonical_endpoint_url) for result in results)))

def _client(path: Path, admin: bool=True, validation_results: Sequence[DownstreamConnectorValidationResult]=(DownstreamConnectorValidationSucceeded(),) * 20, canonical_endpoint_url: str='https://example.test/mcp') -> TestClient:
    settings = APISettings(connector_store={'type': 'sqlite', 'sqlite_path': str(path)}, admin_authentication={'mode': 'simulation', 'simulated_admin': admin})
    app = create_app(settings=settings, connector_registrations=[])
    probe = _probe(validation_results, canonical_endpoint_url)

    def probe_override() -> ScriptedDownstreamMcpProbe:
        return probe
    admin_app = cast(FastAPI, next((route.app for route in app.routes if route.path == '/admin')))
    admin_app.dependency_overrides[get_downstream_connector_probe] = probe_override
    return TestClient(app)

def _payload(token: str='secret') -> dict[str, Any]:
    return {'metadata': {'display_name': 'Alpha', 'capability_description': 'Manage downstream tools', 'public_path': '/mcp/proxies/alpha'}, 'configuration': {'endpoint_url': 'https://example.test/mcp', 'auth_mode': 'static_bearer', 'bearer_token': token}}

def test_openapi_exposes_only_canonical_downstream_mcp_routes(tmp_path: Path) -> None:
    client = _client(tmp_path / 'api.sqlite3')
    response = client.get('/admin/openapi.json')
    assert response.status_code == 200
    paths = response.json()['paths']
    member_path = '/connectors/mcp/{connector_id}'
    assert set(paths[member_path]) == {'get', 'patch', 'delete'}
    assert '/connectors/mcp/{connector_id}/configuration' in paths
    assert set(paths['/connectors/mcp/{connector_id}/configuration']) == {'put'}
    assert '/connectors/mcp/{connector_id}/check' not in paths
    assert '/connectors/mcp/{connector_id}/import' not in paths
    assert '/connectors/mcp/{connector_id}/import-file' not in paths
    assert '/connectors/mcp/{connector_id}/discovery' not in paths
    assert '/connectors/mcp/{connector_id}/oauth/authorization' not in paths
    assert '/oauth/downstream-mcp/callback' not in paths
    assert set(paths['/connectors/mcp/{connector_id}/tools/activation']) == {'get', 'put'}
    assert '/connectors/mcp/{connector_id}/tools/{tool_id}/activation' not in paths
    assert '/connectors/mcp/{connector_id}/tools/invocation-policy' not in paths

@pytest.mark.asyncio
async def test_new_connector_immediately_exposes_probed_catalog(tmp_path: Path) -> None:
    client = _client(tmp_path / 'api.sqlite3')
    created = client.post('/admin/connectors/mcp', json=_payload())
    connector_id = created.json()['connector_id']
    response = client.get(f'/admin/connectors/mcp/{connector_id}/tools')
    assert response.status_code == 200
    assert response.json()['discovered_at'] is not None
    assert response.json()['tools'] == []
    assert created.json()['health']['status'] == 'healthy'

@pytest.mark.asyncio
async def test_create_persists_canonical_endpoint_returned_by_probe(tmp_path: Path) -> None:
    client = _client(tmp_path / 'api.sqlite3', canonical_endpoint_url='https://example.test/mcp/')
    response = client.post('/admin/connectors/mcp', json=_payload())
    assert response.status_code == 201
    assert response.json()['endpoint_url'] == 'https://example.test/mcp/'
    connector_id = response.json()['connector_id']
    persisted = client.get(f'/admin/connectors/mcp/{connector_id}')
    assert persisted.json()['endpoint_url'] == 'https://example.test/mcp/'

@pytest.mark.asyncio
async def test_list_and_detail_discriminate_system_and_overridden_capability_descriptions(tmp_path: Path) -> None:
    client = _client(tmp_path / 'api.sqlite3')
    created = client.post('/admin/connectors/mcp', json=_payload())
    connector_id = created.json()['connector_id']
    system_detail = client.get(f'/admin/connectors/mcp/{connector_id}').json()
    assert system_detail['capability_description_override'] == {'state': 'system', 'revision': 0}
    override_response = client.put(f'/admin/connector-capability-descriptions/downstream_mcp/{connector_id}', json={'action': 'set', 'description': 'Custom downstream capability', 'expected_revision': 0})
    assert override_response.status_code == 200
    expected_override = {'state': 'overridden', 'description': 'Custom downstream capability', 'revision': 1}
    detail = client.get(f'/admin/connectors/mcp/{connector_id}').json()
    connector_list = client.get('/admin/connectors/mcp').json()
    assert detail['capability_description_override'] == expected_override
    assert set(detail) == {'connector_id', 'display_name', 'tool_name_prefix', 'icon_url', 'capability_description', 'base_capability_description', 'effective_capability_description', 'capability_description_override', 'endpoint_url', 'public_path', 'public_url', 'auth_mode', 'header_type', 'custom_header_name', 'credential_configured', 'publication_status', 'health'}
    assert set(connector_list['connectors'][0]) == {'connector_id', 'display_name', 'icon_url', 'auth_mode', 'publication_status', 'health'}
    assert 'capability_description_override' not in connector_list['connectors'][0]

@pytest.mark.asyncio
async def test_create_endpoint_not_found_returns_typed_422_and_persists_nothing(tmp_path: Path) -> None:
    client = _client(tmp_path / 'api.sqlite3', validation_results=(DownstreamConnectorValidationFailed(code='endpoint_not_found'),))
    response = client.post('/admin/connectors/mcp', json=_payload())
    assert response.status_code == 422
    assert response.json()['detail'] == {'code': 'endpoint_not_found', 'message': 'No MCP server was found at that endpoint.', 'phase': 'validation', 'retryable': False, 'context': {}}
    assert client.get('/admin/connectors/mcp').json() == {'connectors': []}

@pytest.mark.asyncio
async def test_failed_update_retains_prior_configuration(tmp_path: Path) -> None:
    client = _client(tmp_path / 'api.sqlite3', validation_results=(DownstreamConnectorValidationSucceeded(), DownstreamConnectorValidationFailed(code='endpoint_not_found')))
    created = client.post('/admin/connectors/mcp', json=_payload()).json()
    response = client.put(f"/admin/connectors/mcp/{created['connector_id']}/configuration", json={'auth_mode': 'static_bearer', 'endpoint_url': 'https://changed.example.test/mcp', 'bearer_token': 'replacement'})
    retained = client.get(f"/admin/connectors/mcp/{created['connector_id']}").json()
    assert response.status_code == 422
    assert response.json()['detail']['code'] == 'endpoint_not_found'
    assert response.json()['detail']['phase'] == 'validation'
    assert retained['display_name'] == 'Alpha'
    assert retained['endpoint_url'] == 'https://example.test/mcp'

@pytest.mark.asyncio
async def test_create_rejects_client_supplied_connector_id(tmp_path: Path) -> None:
    payload = _payload()
    payload['metadata']['connector_id'] = 'alpha'
    response = _client(tmp_path / 'api.sqlite3').post('/admin/connectors/mcp', json=payload)
    assert response.status_code == 422

@pytest.mark.asyncio
async def test_admin_authentication_protects_downstream_connector_routes(tmp_path: Path) -> None:
    response = _client(tmp_path / 'api.sqlite3', admin=False).get('/admin/connectors/mcp')
    assert response.status_code == 403

@pytest.mark.parametrize('retained_bearer_token', ['', None])
@pytest.mark.asyncio
async def test_crud_masks_bearer_and_blank_update_retains_credential(tmp_path: Path, retained_bearer_token: str | None) -> None:
    client = _client(tmp_path / 'api.sqlite3')
    created = client.post('/admin/connectors/mcp', json=_payload())
    assert created.status_code == 201
    connector_id = created.json()['connector_id']
    UUID(connector_id)
    updated = client.patch(f'/admin/connectors/mcp/{connector_id}', json={'display_name': 'Updated', 'capability_description': 'Update downstream records'})
    retained_credential = client.put(f'/admin/connectors/mcp/{connector_id}/configuration', json={'auth_mode': 'static_bearer', 'endpoint_url': 'https://example.test/mcp', 'bearer_token': retained_bearer_token})
    fetched = client.get(f'/admin/connectors/mcp/{connector_id}')
    deleted = client.delete(f'/admin/connectors/mcp/{connector_id}')
    assert 'secret' not in created.text
    assert updated.status_code == 200
    assert retained_credential.status_code == 200
    assert fetched.json()['credential_configured'] is True
    assert fetched.json()['display_name'] == 'Updated'
    assert fetched.json()['capability_description'] == 'Update downstream records'
    assert deleted.status_code == 204
    assert client.get(f'/admin/connectors/mcp/{connector_id}').status_code == 404

@pytest.mark.parametrize('endpoint', ['http://example.test/mcp', 'https://user:pass@example.test/mcp', 'not-a-url'])
@pytest.mark.asyncio
async def test_create_rejects_invalid_endpoint_urls(tmp_path: Path, endpoint: str) -> None:
    payload = _payload()
    payload['configuration']['endpoint_url'] = endpoint
    assert _client(tmp_path / 'api.sqlite3').post('/admin/connectors/mcp', json=payload).status_code == 422

@pytest.mark.asyncio
async def test_duplicate_display_names_are_allowed_but_public_paths_conflict(tmp_path: Path) -> None:
    client = _client(tmp_path / 'api.sqlite3')
    assert client.post('/admin/connectors/mcp', json=_payload()).status_code == 201
    duplicate_path = client.post('/admin/connectors/mcp', json=_payload())
    second_payload = _payload()
    second_payload['metadata']['public_path'] = '/mcp/proxies/alpha-two'
    duplicate_name = client.post('/admin/connectors/mcp', json=second_payload)
    assert duplicate_path.status_code == 409
    assert duplicate_path.json()['detail']['code'] == 'public_path_conflict'
    assert duplicate_name.status_code == 201
    assert duplicate_name.json()['display_name'] == 'Alpha'

@pytest.mark.asyncio
async def test_create_rejects_missing_bearer_and_missing_ids_return_not_found(tmp_path: Path) -> None:
    client = _client(tmp_path / 'api.sqlite3')
    assert client.post('/admin/connectors/mcp', json=_payload('')).status_code == 422
    assert client.get('/admin/connectors/mcp/missing').status_code == 404
    assert client.delete('/admin/connectors/mcp/missing').status_code == 404

def _oauth_payload() -> dict[str, Any]:
    return {'metadata': {'display_name': 'OAuth Alpha', 'capability_description': 'Authorize downstream tools', 'public_path': '/mcp/proxies/oauth-alpha'}, 'configuration': {'endpoint_url': 'https://oauth.example.test/mcp', 'auth_mode': 'mcp_oauth'}}

@pytest.mark.asyncio
async def test_create_rejects_removed_mcp_oauth_auth_mode(tmp_path: Path) -> None:
    response = _client(tmp_path / 'api.sqlite3').post('/admin/connectors/mcp', json=_oauth_payload())
    assert response.status_code == 422

@pytest.mark.asyncio
async def test_removed_oauth_routes_return_not_found(tmp_path: Path) -> None:
    client = _client(tmp_path / 'api.sqlite3')
    assert client.put('/admin/connectors/mcp/alpha/oauth/authorization').status_code == 404
    assert client.delete('/admin/connectors/mcp/alpha/oauth/authorization').status_code == 404
    assert client.get('/oauth/downstream-mcp/callback').status_code == 404

@pytest.mark.asyncio
async def test_publication_requires_successful_discovery_and_unpublish_is_idempotent(tmp_path: Path) -> None:
    client = _client(tmp_path / 'api.sqlite3')
    created = client.post('/admin/connectors/mcp', json=_payload())
    assert created.status_code == 201
    connector_id = created.json()['connector_id']
    assert client.put(f'/admin/connectors/mcp/{connector_id}/publication').status_code == 409
    response = client.delete(f'/admin/connectors/mcp/{connector_id}/publication')
    assert response.json()['publication_status'] == 'unpublished'

@pytest.mark.asyncio
async def test_connector_list_exposes_the_discovered_server_icon(tmp_path: Path) -> None:
    database_path = tmp_path / 'api.sqlite3'
    client = _client(database_path)
    created = client.post('/admin/connectors/mcp', json=_payload())
    connector_id = created.json()['connector_id']
    await ToolCatalogStoreService(create_sqlite_runtime(database_path).database, TOOL_CATALOG_TABLE).replace(ReplaceToolCatalog(snapshot=ToolCatalogSnapshot(connector_id=connector_id, discovered_at=datetime(2026, 1, 2, tzinfo=UTC), tools=(), server_icons=(DiscoveredServerIcon(src='https://computerlove.tech/icon.png'),))))
    response = client.get('/admin/connectors/mcp')
    assert response.status_code == 200
    assert response.json()['connectors'][0]['icon_url'] == 'https://computerlove.tech/icon.png'

@pytest.mark.asyncio
async def test_connector_lists_discovered_tools_with_persisted_activation_status(tmp_path: Path) -> None:
    database_path = tmp_path / 'api.sqlite3'
    client = _client(database_path)
    created = client.post('/admin/connectors/mcp', json=_payload())
    connector_id = created.json()['connector_id']
    await ToolCatalogStoreService(create_sqlite_runtime(database_path).database, TOOL_CATALOG_TABLE).replace(ReplaceToolCatalog(snapshot=ToolCatalogSnapshot(connector_id=connector_id, discovered_at=datetime(2026, 1, 2, tzinfo=UTC), tools=(DiscoveredToolWithoutOutputSchema(identity=ToolIdentity(connector_id=connector_id, downstream_name='echo'), title='Echo', description='Echoes the supplied message', input_schema={'type': 'object'}),))))
    activation = client.put(f'/admin/connectors/mcp/{connector_id}/tools/activation', json={'tools': [{'tool_id': 'echo', 'activation_status': 'enabled'}]})
    response = client.get(f'/admin/connectors/mcp/{connector_id}/tools')
    assert activation.status_code == 200
    assert activation.json() == {'connector_id': connector_id, 'tools': [{'tool_id': 'echo', 'activation_status': 'enabled', 'invocation_mode': 'direct', 'policy_revision': 0}]}
    assert response.status_code == 200
    assert response.json()['tools'][0]['activation_status'] == 'enabled'
    rejected = client.put(f'/admin/connectors/mcp/{connector_id}/tools/activation', json={'tools': [{'tool_id': 'echo', 'activation_status': 'disabled'}, {'tool_id': 'missing', 'activation_status': 'enabled'}]})
    retained = client.get(f'/admin/connectors/mcp/{connector_id}/tools')
    assert rejected.status_code == 404
    assert retained.json()['tools'][0]['activation_status'] == 'enabled'

async def _downstream_client_with_tool(tmp_path: Path) -> tuple[TestClient, str]:
    database_path = tmp_path / 'api.sqlite3'
    client = _client(database_path)
    connector_id = client.post('/admin/connectors/mcp', json=_payload()).json()['connector_id']
    await ToolCatalogStoreService(create_sqlite_runtime(database_path).database, TOOL_CATALOG_TABLE).replace(ReplaceToolCatalog(snapshot=ToolCatalogSnapshot(connector_id=connector_id, discovered_at=datetime(2026, 1, 2, tzinfo=UTC), tools=(DiscoveredToolWithoutOutputSchema(identity=ToolIdentity(connector_id=connector_id, downstream_name='echo'), title='Echo', description='Echo', input_schema={'type': 'object'}),))))
    return (client, connector_id)

@pytest.mark.asyncio
async def test_downstream_activation_route_supports_partial_combined_and_revision_updates(tmp_path: Path) -> None:
    (client, connector_id) = await _downstream_client_with_tool(tmp_path)
    path = f'/admin/connectors/mcp/{connector_id}/tools/activation'
    policy_only = client.put(path, json={'tools': [{'tool_id': 'echo', 'invocation_mode': 'ask', 'expected_policy_revision': 0}]})
    activation_only = client.put(path, json={'tools': [{'tool_id': 'echo', 'activation_status': 'enabled'}]})
    combined = client.put(path, json={'tools': [{'tool_id': 'echo', 'activation_status': 'disabled', 'invocation_mode': 'direct', 'expected_policy_revision': 1}]})
    assert policy_only.json()['tools'] == [{'tool_id': 'echo', 'activation_status': 'disabled', 'invocation_mode': 'ask', 'policy_revision': 1}]
    assert activation_only.json()['tools'] == [{'tool_id': 'echo', 'activation_status': 'enabled', 'invocation_mode': 'ask', 'policy_revision': 1}]
    assert combined.json()['tools'] == [{'tool_id': 'echo', 'activation_status': 'disabled', 'invocation_mode': 'direct', 'policy_revision': 2}]

@pytest.mark.asyncio
async def test_downstream_activation_route_handles_noop_conflict_and_unknown_atomically(tmp_path: Path) -> None:
    (client, connector_id) = await _downstream_client_with_tool(tmp_path)
    path = f'/admin/connectors/mcp/{connector_id}/tools/activation'
    direct = client.put(path, json={'tools': [{'tool_id': 'echo', 'invocation_mode': 'direct', 'expected_policy_revision': 0}]})
    stale = client.put(path, json={'tools': [{'tool_id': 'echo', 'invocation_mode': 'ask', 'expected_policy_revision': 1}]})
    unknown = client.put(path, json={'tools': [{'tool_id': 'echo', 'activation_status': 'enabled'}, {'tool_id': 'missing', 'invocation_mode': 'ask', 'expected_policy_revision': 0}]})
    assert direct.json()['tools'][0]['policy_revision'] == 0
    assert stale.status_code == 409
    assert stale.json() == {'code': 'invocation_policy_revision_conflict', 'conflicts': [{'tool_id': 'echo', 'expected_revision': 1, 'current_mode': 'direct', 'current_revision': 0}]}
    assert unknown.status_code == 404
    assert client.get(path).json()['tools'][0] == {'tool_id': 'echo', 'activation_status': 'disabled', 'invocation_mode': 'direct', 'policy_revision': 0}

@pytest.mark.parametrize('item', [{'tool_id': 'echo'}, {'tool_id': 'echo', 'invocation_mode': 'ask'}, {'tool_id': 'echo', 'expected_policy_revision': 0}, {'tool_id': 'echo', 'invocation_mode': 'ask', 'expected_policy_revision': -1}])
@pytest.mark.asyncio
async def test_downstream_activation_route_rejects_malformed_partial_items(tmp_path: Path, item: dict[str, Any]) -> None:
    (client, connector_id) = await _downstream_client_with_tool(tmp_path)
    path = f'/admin/connectors/mcp/{connector_id}/tools/activation'
    response = client.put(path, json={'tools': [item]})
    duplicate = client.put(path, json={'tools': [{'tool_id': 'echo', 'activation_status': 'enabled'}, {'tool_id': 'echo', 'activation_status': 'disabled'}]})
    assert response.status_code == 422
    assert duplicate.status_code == 422

@pytest.mark.asyncio
async def test_published_downstream_connector_appears_in_assignable_permission_targets(tmp_path: Path) -> None:
    database_path = tmp_path / 'api.sqlite3'
    client = _client(database_path)
    created = client.post('/admin/connectors/mcp', json=_payload())
    assert created.status_code == 201
    connector_id = created.json()['connector_id']
    await ToolCatalogStoreService(create_sqlite_runtime(database_path).database, TOOL_CATALOG_TABLE).replace(ReplaceToolCatalog(snapshot=ToolCatalogSnapshot(connector_id=connector_id, discovered_at=datetime(2026, 1, 2, tzinfo=UTC), tools=(DiscoveredToolWithoutOutputSchema(identity=ToolIdentity(connector_id=connector_id, downstream_name='echo'), title='Echo', description='Echoes the supplied message', input_schema={'type': 'object'}),))))
    publication = client.put(f'/admin/connectors/mcp/{connector_id}/publication')
    activation = client.put(f'/admin/connectors/mcp/{connector_id}/tools/activation', json={'tools': [{'tool_id': 'echo', 'activation_status': 'enabled'}]})
    response = client.get('/admin/mcp-permissions/assignable-targets')
    assert publication.status_code == 200
    assert activation.status_code == 200
    assert response.status_code == 200
    assert response.json() == {'connectors': [{'connector_id': connector_id, 'display_name': 'Alpha'}], 'capabilities': [{'connector_id': connector_id, 'capability_kind': 'tool', 'capability_key': 'echo', 'display_name': 'Echo'}]}
