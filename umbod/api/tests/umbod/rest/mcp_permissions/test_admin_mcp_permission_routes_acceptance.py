from tests.persistence_runtime import prepared_sqlite_runtime
import json
from pathlib import Path
import anyio
import pytest
from fastapi.testclient import TestClient
from umbod.rest.main import create_app
from umbod.rest.settings import APISettings
from tests.support.connector_plugins import TestConnectorPlugin
DIFF_UPDATE_PERMISSION_CHANGE_METADATA: list[dict[str, str]] = [{'group_id': 'engineering', 'action': 'grant', 'target_kind': 'tool', 'connector_id': 'test', 'operation_name': 'get_default_response', 'capability_kind': 'tool', 'capability_key': 'get_default_response'}, {'group_id': 'engineering', 'action': 'grant', 'target_kind': 'tool', 'connector_id': 'test', 'operation_name': 'echo', 'capability_kind': 'tool', 'capability_key': 'echo'}, {'group_id': 'engineering', 'action': 'revoke', 'target_kind': 'tool', 'connector_id': 'test', 'operation_name': 'get_default_response', 'capability_kind': 'tool', 'capability_key': 'get_default_response'}]

class FastApiAdminMcpPermissionApi:

    def __init__(self, client: TestClient) -> None:
        self.client = client

    def list_groups(self) -> dict[str, object]:
        return self.client.get('/admin/mcp-permissions/groups').json()

    def get_group(self, group_id: str) -> dict[str, object]:
        return self.client.get(f'/admin/mcp-permissions/groups/{group_id}').json()

    def grant_connector(self, group_id: str, connector_id: str) -> tuple[int, dict[str, object]]:
        return self.update_group(group_id, {'connectors': [{'connector_id': connector_id, 'permission_status': 'enabled'}], 'capabilities': []})

    def revoke_connector(self, group_id: str, connector_id: str) -> tuple[int, dict[str, object]]:
        return self.update_group(group_id, {'connectors': [{'connector_id': connector_id, 'permission_status': 'disabled'}], 'capabilities': []})

    def grant_tool(self, group_id: str, connector_id: str, operation_name: str) -> tuple[int, dict[str, object]]:
        return self.update_group(group_id, {'connectors': [], 'capabilities': [{'connector_id': connector_id, 'capability_kind': 'tool', 'capability_key': operation_name, 'permission_status': 'enabled'}]})

    def revoke_tool(self, group_id: str, connector_id: str, operation_name: str) -> tuple[int, dict[str, object]]:
        return self.update_group(group_id, {'connectors': [], 'capabilities': [{'connector_id': connector_id, 'capability_kind': 'tool', 'capability_key': operation_name, 'permission_status': 'disabled'}]})

    def update_group(self, group_id: str, payload: dict[str, object]) -> tuple[int, dict[str, object]]:
        response = self.client.put(f'/admin/mcp-permissions/groups/{group_id}/permissions', json=payload)
        return (response.status_code, response.json())

    def list_system_events(self, event_type: str) -> list[dict[str, object]]:
        response = self.client.get(f'/system/events?after_sequence=0&limit=100&event_type={event_type}')
        assert response.status_code == 200
        return response.json()

    def configure_test_connector(self) -> tuple[int, dict[str, object]]:
        response = self.client.put('/admin/connectors/catalog/test/configuration', json={'configuration': {'instance_name': 'Demo', 'api_key': 'test-key', 'default_response': 'Hello from test connector'}})
        return (response.status_code, response.json())

    def publish_test_connector(self) -> tuple[int, dict[str, object]]:
        response = self.client.put('/admin/connectors/catalog/test/publication')
        return (response.status_code, response.json())

@pytest.fixture
def api(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> FastApiAdminMcpPermissionApi:
    return _create_api(tmp_path, monkeypatch, True)

@pytest.fixture
def unassignable_api(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> FastApiAdminMcpPermissionApi:
    return _create_api(tmp_path, monkeypatch, False)

def test_openapi_exposes_only_aggregate_group_permission_mutations(api: FastApiAdminMcpPermissionApi) -> None:
    response = api.client.get('/admin/openapi.json')
    assert response.status_code == 200
    paths = response.json()['paths']
    assert set(paths['/mcp-permissions/groups/{group_id}']) == {'get', 'post', 'delete'}
    assert set(paths['/mcp-permissions/groups/{group_id}/permissions']) == {'put'}
    assert '/mcp-permissions/groups/{group_id}/connectors/{connector_id}' not in paths
    assert '/mcp-permissions/groups/{group_id}/tools' not in paths
    assert '/mcp-permissions/groups/{group_id}/tools/{connector_id}/{operation_name}' not in paths

def test_admin_can_grant_and_revoke_connector_permission(api: FastApiAdminMcpPermissionApi) -> None:
    (status_code, grant) = api.grant_connector('engineering', 'test')
    assert status_code == 200
    assert grant['status'] == 'applied'
    assert api.get_group('engineering') == {'group_id': 'engineering', 'connector_ids': ['test'], 'capabilities': []}
    (status_code, revoke) = api.revoke_connector('engineering', 'test')
    assert status_code == 200
    assert revoke['status'] == 'applied'
    assert api.get_group('engineering') == {'group_id': 'engineering', 'connector_ids': [], 'capabilities': []}

def test_admin_can_grant_and_revoke_tool_permission(api: FastApiAdminMcpPermissionApi) -> None:
    (status_code, grant) = api.grant_tool('engineering', 'test', 'get_default_response')
    assert status_code == 200
    assert grant['status'] == 'applied'
    assert api.get_group('engineering') == {'group_id': 'engineering', 'connector_ids': [], 'capabilities': [{'connector_id': 'test', 'capability_kind': 'tool', 'capability_key': 'get_default_response'}]}
    (status_code, revoke) = api.revoke_tool('engineering', 'test', 'get_default_response')
    assert status_code == 200
    assert revoke['status'] == 'applied'
    assert api.get_group('engineering') == {'group_id': 'engineering', 'connector_ids': [], 'capabilities': []}

def test_admin_can_update_group_permissions_with_mixed_diff(api: FastApiAdminMcpPermissionApi) -> None:
    api.grant_tool('engineering', 'test', 'get_default_response')
    (status_code, save) = api.update_group('engineering', {'connectors': [{'connector_id': 'test', 'permission_status': 'enabled'}], 'capabilities': [{'connector_id': 'test', 'capability_kind': 'tool', 'capability_key': 'echo', 'permission_status': 'enabled'}, {'connector_id': 'test', 'capability_kind': 'tool', 'capability_key': 'get_default_response', 'permission_status': 'disabled'}]})
    assert status_code == 200
    assert save['status'] == 'applied'
    assert api.get_group('engineering') == {'group_id': 'engineering', 'connector_ids': ['test'], 'capabilities': [{'connector_id': 'test', 'capability_kind': 'tool', 'capability_key': 'echo'}]}

def test_partial_update_mixes_enable_and_disable_without_changing_omitted_permissions(api: FastApiAdminMcpPermissionApi) -> None:
    api.grant_connector('engineering', 'test')
    api.grant_tool('engineering', 'test', 'get_default_response')
    (status_code, result) = api.update_group('engineering', {'connectors': [{'connector_id': 'test', 'permission_status': 'disabled'}], 'capabilities': [{'connector_id': 'test', 'capability_kind': 'tool', 'capability_key': 'echo', 'permission_status': 'enabled'}]})
    assert status_code == 200
    assert result == {'status': 'applied', 'group_id': 'engineering'}
    assert api.get_group('engineering') == {'group_id': 'engineering', 'connector_ids': [], 'capabilities': [{'connector_id': 'test', 'capability_kind': 'tool', 'capability_key': 'echo'}, {'connector_id': 'test', 'capability_kind': 'tool', 'capability_key': 'get_default_response'}]}

@pytest.mark.parametrize('payload', [{'connectors': [], 'capabilities': []}, {'connectors': [{'connector_id': 'test', 'permission_status': 'enabled'}, {'connector_id': 'test', 'permission_status': 'disabled'}], 'capabilities': []}, {'connectors': [], 'capabilities': [{'connector_id': 'test', 'capability_kind': 'tool', 'capability_key': 'echo', 'permission_status': 'enabled'}, {'connector_id': 'test', 'capability_kind': 'tool', 'capability_key': 'echo', 'permission_status': 'disabled'}]}])
def test_partial_update_rejects_empty_and_duplicate_payloads(api: FastApiAdminMcpPermissionApi, payload: dict[str, object]) -> None:
    (status_code, _) = api.update_group('engineering', payload)
    assert status_code == 422

def test_partial_update_unknown_target_causes_no_partial_mutation(api: FastApiAdminMcpPermissionApi) -> None:
    api.grant_tool('engineering', 'test', 'get_default_response')
    (status_code, response) = api.update_group('engineering', {'connectors': [{'connector_id': 'test', 'permission_status': 'enabled'}], 'capabilities': [{'connector_id': 'test', 'capability_kind': 'tool', 'capability_key': 'missing', 'permission_status': 'enabled'}]})
    assert status_code == 404
    assert response == {'detail': 'Unknown connector capability'}
    assert api.get_group('engineering') == {'group_id': 'engineering', 'connector_ids': [], 'capabilities': [{'connector_id': 'test', 'capability_kind': 'tool', 'capability_key': 'get_default_response'}]}

def test_partial_update_registers_missing_group(api: FastApiAdminMcpPermissionApi) -> None:
    (status_code, _) = api.update_group('new-team', {'connectors': [{'connector_id': 'test', 'permission_status': 'enabled'}], 'capabilities': []})
    assert status_code == 200
    assert api.get_group('new-team') == {'group_id': 'new-team', 'connector_ids': ['test'], 'capabilities': []}
    assert 'new-team' in [group['group_id'] for group in api.list_groups()['groups']]

def test_repeated_partial_update_is_idempotent_and_emits_only_effective_events(api: FastApiAdminMcpPermissionApi) -> None:
    payload = {'connectors': [], 'capabilities': [{'connector_id': 'test', 'capability_kind': 'tool', 'capability_key': 'echo', 'permission_status': 'enabled'}]}
    (first_status, _) = api.update_group('engineering', payload)
    (second_status, _) = api.update_group('engineering', payload)
    events = api.list_system_events('mcp.group_permission.changed')
    assert first_status == 200
    assert second_status == 200
    assert api.get_group('engineering')['capabilities'] == [{'connector_id': 'test', 'capability_kind': 'tool', 'capability_key': 'echo'}]
    assert [event['event']['metadata'] for event in events] == [{'group_id': 'engineering', 'action': 'grant', 'target_kind': 'tool', 'connector_id': 'test', 'operation_name': 'echo', 'capability_kind': 'tool', 'capability_key': 'echo'}]

def test_admin_can_list_all_group_permissions(api: FastApiAdminMcpPermissionApi) -> None:
    api.grant_connector('engineering', 'test')
    api.grant_tool('support', 'test', 'echo')
    assert api.list_groups() == {'groups': [{'group_id': 'engineering'}, {'group_id': 'support'}]}

def test_unknown_permission_targets_are_rejected(api: FastApiAdminMcpPermissionApi) -> None:
    (connector_status, connector_response) = api.grant_connector('engineering', 'missing')
    (tool_status, tool_response) = api.grant_tool('engineering', 'test', 'missing')
    assert connector_status == 404
    assert connector_response == {'detail': 'Unknown connector'}
    assert tool_status == 404
    assert tool_response == {'detail': 'Unknown connector capability'}
    assert api.get_group('engineering') == {'group_id': 'engineering', 'connector_ids': [], 'capabilities': []}

def test_permission_targets_require_configured_published_connector_and_enabled_tool(unassignable_api: FastApiAdminMcpPermissionApi) -> None:
    _assert_test_connector_and_echo_tool_are_rejected(unassignable_api)
    (configure_status, _) = unassignable_api.configure_test_connector()
    assert configure_status == 200
    _assert_test_connector_and_echo_tool_are_rejected(unassignable_api)
    (publish_status, _) = unassignable_api.publish_test_connector()
    (published_connector_status, published_connector_response) = unassignable_api.grant_connector('engineering', 'test')
    (published_tool_status, published_tool_response) = unassignable_api.grant_tool('engineering', 'test', 'echo')
    assert publish_status == 200
    assert published_connector_status == 200
    assert published_connector_response == {'status': 'applied', 'group_id': 'engineering'}
    assert published_tool_status == 404
    assert published_tool_response == {'detail': 'Unknown connector capability'}
    (enable_status, _) = _enable_tool(unassignable_api, 'test', 'echo')
    (enabled_tool_status, enabled_tool_response) = unassignable_api.grant_tool('engineering', 'test', 'echo')
    assert enable_status == 200
    assert enabled_tool_status == 200
    assert enabled_tool_response == {'status': 'applied', 'group_id': 'engineering'}

def _assert_test_connector_and_echo_tool_are_rejected(api: FastApiAdminMcpPermissionApi) -> None:
    (connector_status, connector_response) = api.grant_connector('engineering', 'test')
    (tool_status, tool_response) = api.grant_tool('engineering', 'test', 'echo')
    assert connector_status == 404
    assert connector_response == {'detail': 'Unknown connector'}
    assert tool_status == 404
    assert tool_response == {'detail': 'Unknown connector capability'}

def test_diff_update_rejects_disabled_tool_then_succeeds_after_enabling_tool(unassignable_api: FastApiAdminMcpPermissionApi) -> None:
    unassignable_api.configure_test_connector()
    unassignable_api.publish_test_connector()
    (disabled_status, disabled_response) = unassignable_api.update_group('engineering', {'connectors': [{'connector_id': 'test', 'permission_status': 'enabled'}], 'capabilities': [{'connector_id': 'test', 'capability_kind': 'tool', 'capability_key': 'echo', 'permission_status': 'enabled'}]})
    assert disabled_status == 404
    assert disabled_response == {'detail': 'Unknown connector capability'}
    (enable_status, _) = _enable_tool(unassignable_api, 'test', 'echo')
    (enabled_status, enabled_response) = unassignable_api.update_group('engineering', {'connectors': [{'connector_id': 'test', 'permission_status': 'enabled'}], 'capabilities': [{'connector_id': 'test', 'capability_kind': 'tool', 'capability_key': 'echo', 'permission_status': 'enabled'}]})
    assert enable_status == 200
    assert enabled_status == 200
    assert enabled_response == {'status': 'applied', 'group_id': 'engineering'}

def test_diff_update_openapi_permissions_can_revoke_and_grant_tools(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    availability_path = tmp_path / 'connector-availability.json'
    availability_path.write_text('{"connectors": []}', encoding='utf-8')
    monkeypatch.setenv('UMBOD_CONNECTOR_DEPLOYMENT_CONFIGURATION_PATH', str(availability_path))
    settings = APISettings(admin_authentication={'mode': 'simulation', 'simulated_admin': True}, connector_store={'type': 'sqlite', 'sqlite_path': str(tmp_path / 'openapi.sqlite3')})
    api = FastApiAdminMcpPermissionApi(TestClient(create_app(settings=settings, connector_registrations=[])))
    created = api.client.post('/admin/connectors/openapi', json={'display_name': 'Inventory', 'capability_description': 'Manage inventory resources'})
    connector_id = str(created.json()['connector_id'])
    document = {'openapi': '3.1.0', 'info': {'title': 'Inventory', 'version': '1'}, 'servers': [{'url': 'https://api.example.com'}], 'paths': {'/items': {'get': {'operationId': 'listItems', 'responses': {'200': {'description': 'ok'}}}, 'post': {'operationId': 'createItem', 'responses': {'200': {'description': 'ok'}}}}}}
    assert api.client.post(f'/admin/connectors/openapi/{connector_id}/imports', json={'document': document, 'approved_hosts': ['api.example.com']}).status_code == 201
    assert api.client.put(f'/admin/connectors/openapi/{connector_id}/publication').status_code == 200
    assert api.client.put(f'/admin/connectors/openapi/{connector_id}/tools/activation', json={'tools': [{'tool_id': operation_id, 'activation_status': 'enabled'} for operation_id in ('listItems', 'createItem')]}).status_code == 200
    assert api.grant_tool('engineering', connector_id, 'listItems')[0] == 200
    (saved_status, saved) = api.update_group('engineering', {'connectors': [{'connector_id': connector_id, 'permission_status': 'enabled'}], 'capabilities': [{'connector_id': connector_id, 'capability_kind': 'tool', 'capability_key': 'createItem', 'permission_status': 'enabled'}, {'connector_id': connector_id, 'capability_kind': 'tool', 'capability_key': 'listItems', 'permission_status': 'disabled'}]})
    assert saved_status == 200
    assert saved == {'status': 'applied', 'group_id': 'engineering'}
    assert api.get_group('engineering') == {'group_id': 'engineering', 'connector_ids': [connector_id], 'capabilities': [{'connector_id': connector_id, 'capability_kind': 'tool', 'capability_key': 'createItem'}]}

def test_admin_can_list_assignable_permission_targets(unassignable_api: FastApiAdminMcpPermissionApi) -> None:
    initial_response = unassignable_api.client.get('/admin/mcp-permissions/assignable-targets')
    assert initial_response.status_code == 200
    assert initial_response.json() == {'connectors': [], 'capabilities': []}
    unassignable_api.configure_test_connector()
    unassignable_api.publish_test_connector()
    _enable_tool(unassignable_api, 'test', 'echo')
    assigned_response = unassignable_api.client.get('/admin/mcp-permissions/assignable-targets')
    assert assigned_response.status_code == 200
    assert assigned_response.json() == {'connectors': [{'connector_id': 'test', 'display_name': 'Test Connector'}], 'capabilities': [{'connector_id': 'test', 'capability_kind': 'tool', 'capability_key': 'echo', 'display_name': 'Echo'}]}

def test_non_admin_cannot_manage_permissions(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    availability_path = tmp_path / 'connector-availability.json'
    availability_path.write_text(json.dumps({'connectors': [{'id': 'test'}]}), encoding='utf-8')
    monkeypatch.setenv('UMBOD_CONNECTOR_DEPLOYMENT_CONFIGURATION_PATH', str(availability_path))
    settings = APISettings(admin_authentication={'mode': 'jwt', 'jwt_header_name': 'X-Forwarded-Access-Token', 'jwks_url': 'https://identity.example.com/.well-known/jwks.json', 'membership_claim': 'groups', 'required_membership': 'umbod-admins'}, connector_store={'type': 'sqlite', 'sqlite_path': str(tmp_path / 'umbod.sqlite3')})
    response = TestClient(create_app(settings=settings, connector_registrations=[TestConnectorPlugin.registration()])).get('/admin/mcp-permissions/groups')
    assert response.status_code == 401

def test_permissions_persist_through_recreated_app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    first_api = _create_api(tmp_path, monkeypatch, True)
    first_api.grant_tool('engineering', 'test', 'echo')
    second_api = _create_api(tmp_path, monkeypatch, True)
    assert second_api.get_group('engineering') == {'group_id': 'engineering', 'connector_ids': [], 'capabilities': [{'connector_id': 'test', 'capability_kind': 'tool', 'capability_key': 'echo'}]}

def test_runtime_can_read_current_group_permissions(api: FastApiAdminMcpPermissionApi) -> None:
    api.grant_tool('engineering', 'test', 'echo')
    response = api.client.get('/system/mcp-permissions/groups')
    assert response.status_code == 200
    assert response.json() == {'groups': [{'group_id': 'engineering', 'connector_ids': [], 'capabilities': [{'connector_id': 'test', 'capability_kind': 'tool', 'capability_key': 'echo'}]}]}

def test_admin_connector_grant_and_revoke_publish_permission_change_events(api: FastApiAdminMcpPermissionApi) -> None:
    (grant_status, _) = api.grant_connector('engineering', 'test')
    (revoke_status, _) = api.revoke_connector('engineering', 'test')
    events = api.list_system_events('mcp.group_permission.changed')
    assert grant_status == 200
    assert revoke_status == 200
    assert [stream_event['event']['event_type'] for stream_event in events] == ['mcp.group_permission.changed', 'mcp.group_permission.changed']
    assert [stream_event['event']['metadata'] for stream_event in events] == [{'group_id': 'engineering', 'action': 'grant', 'target_kind': 'connector', 'connector_id': 'test'}, {'group_id': 'engineering', 'action': 'revoke', 'target_kind': 'connector', 'connector_id': 'test'}]

def test_admin_tool_grant_and_revoke_publish_permission_change_events(api: FastApiAdminMcpPermissionApi) -> None:
    (grant_status, _) = api.grant_tool('engineering', 'test', 'echo')
    (revoke_status, _) = api.revoke_tool('engineering', 'test', 'echo')
    events = api.list_system_events('mcp.group_permission.changed')
    assert grant_status == 200
    assert revoke_status == 200
    assert [stream_event['event']['event_type'] for stream_event in events] == ['mcp.group_permission.changed', 'mcp.group_permission.changed']
    assert [stream_event['event']['metadata'] for stream_event in events] == [{'group_id': 'engineering', 'action': 'grant', 'target_kind': 'tool', 'connector_id': 'test', 'operation_name': 'echo', 'capability_kind': 'tool', 'capability_key': 'echo'}, {'group_id': 'engineering', 'action': 'revoke', 'target_kind': 'tool', 'connector_id': 'test', 'operation_name': 'echo', 'capability_kind': 'tool', 'capability_key': 'echo'}]

def test_admin_diff_update_publishes_permission_change_events(api: FastApiAdminMcpPermissionApi) -> None:
    api.grant_tool('engineering', 'test', 'get_default_response')
    (status_code, _) = api.update_group('engineering', {'connectors': [], 'capabilities': [{'connector_id': 'test', 'capability_kind': 'tool', 'capability_key': 'echo', 'permission_status': 'enabled'}, {'connector_id': 'test', 'capability_kind': 'tool', 'capability_key': 'get_default_response', 'permission_status': 'disabled'}]})
    events = api.list_system_events('mcp.group_permission.changed')
    assert status_code == 200
    assert [stream_event['event']['metadata'] for stream_event in events] == DIFF_UPDATE_PERMISSION_CHANGE_METADATA

def _create_api(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, provision_assignable_test_connector: bool) -> FastApiAdminMcpPermissionApi:
    availability_path = tmp_path / 'connector-availability.json'
    availability_path.write_text(json.dumps({'connectors': [{'id': 'test'}]}), encoding='utf-8')
    monkeypatch.setenv('UMBOD_CONNECTOR_DEPLOYMENT_CONFIGURATION_PATH', str(availability_path))
    database_path = tmp_path / 'umbod.sqlite3'
    settings = APISettings(admin_authentication={'mode': 'simulation', 'simulated_admin': True}, connector_store={'type': 'sqlite', 'sqlite_path': str(database_path)})
    anyio.run(prepared_sqlite_runtime, database_path)
    api = FastApiAdminMcpPermissionApi(TestClient(create_app(settings=settings, connector_registrations=[TestConnectorPlugin.registration()])))
    if provision_assignable_test_connector:
        _provision_assignable_test_connector(api)
    return api

def _provision_assignable_test_connector(api: FastApiAdminMcpPermissionApi) -> None:
    api.configure_test_connector()
    api.publish_test_connector()
    _enable_tool(api, 'test', 'echo')
    _enable_tool(api, 'test', 'get_default_response')

def _enable_tool(api: FastApiAdminMcpPermissionApi, connector_id: str, operation_name: str) -> tuple[int, dict[str, object]]:
    response = api.client.put(f'/admin/connectors/catalog/{connector_id}/tools/activation', json={'tools': [{'tool_id': operation_name, 'activation_status': 'enabled'}]})
    return (response.status_code, response.json())
