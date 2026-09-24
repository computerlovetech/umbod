from umbod.core.publishing.stores.schema import PUBLICATION_STATE_TABLE
from umbod.core.publishing.stores.service import ConnectorPublishingStoreService
from tests.persistence_runtime import create_inmemory_runtime
from inspect import isawaitable
from importlib import import_module
from pathlib import Path
from typing import Any
import pytest
from fastmcp import Client
from jsonschema.exceptions import SchemaError
from pydantic import ConfigDict, Field, SecretStr
from umbod_sdk.connectors.proxies import Model
from tests.mcp_fixtures import build_test_mcp
from umbod.core.configuration import InMemoryConnectorCurrentConfigurationStore
from umbod.core.connectors.native.deployment.availability import DeploymentConnectorAvailability
from umbod.core.connectors.native.runtime import assemble_connector_runtime, connector_tool_mappings
from umbod_sdk.connectors.discovery import load_connector_plugins

class ProjectBoardConfiguration(Model):
    model_config = ConfigDict(extra='forbid')
    workspace_name: str = Field(description='Workspace name shown to Umbod administrators.')
    api_token: SecretStr = Field(description='API token used to connect to Project Board.')

class SearchTasksRequest(Model):
    project_id: str = Field(description='Project identifier to search within.')
    query: str = Field(description='Search query used to match task text.')

def test_external_developer_can_define_configurable_mcp_connector_as_instantiated_object() -> None:
    plugin_api = import_module('umbod_sdk.connectors.plugin_api')
    plugin = _project_board_connector(plugin_api)
    runtime = assemble_connector_runtime(plugins=[plugin], availability=DeploymentConnectorAvailability.from_mapping({'connectors': [{'id': 'project_board'}]}), configuration_store=InMemoryConnectorCurrentConfigurationStore(), publishing_store=ConnectorPublishingStoreService(create_inmemory_runtime().database, PUBLICATION_STATE_TABLE))
    assert runtime.connector_registrations[0]['id'] == 'project_board'
    assert runtime.connector_registrations[0]['icon_data_url'] is None
    assert runtime.connector_registrations[0]['configuration_schema'] is ProjectBoardConfiguration
    assert [mapping.operation_name for mapping in runtime.connector_tool_mappings] == ['list_tasks']

@pytest.mark.asyncio
async def test_decorated_connector_function_is_available_as_published_mcp_tool() -> None:
    plugin_api = import_module('umbod_sdk.connectors.plugin_api')
    (configuration_store, publishing_store, runtime) = await _published_project_board_context_for_plugin(_project_board_connector(plugin_api))
    mcp = await build_test_mcp(None, None, connector_registrations=runtime.connector_registrations, connector_configuration_store=configuration_store, connector_publishing_store=publishing_store, connector_tool_mappings=runtime.connector_tool_mappings)
    async with Client(mcp) as client:
        tools = await client.list_tools()
        result = await client.call_tool('project_board_list_tasks', {'project_id': 'PB-1'})
    tools_by_name = {tool.name: tool for tool in tools}
    tool_schema = tools_by_name['project_board_list_tasks'].input_schema
    assert tools_by_name['project_board_list_tasks'].description == 'List tasks in a Project Board project.'
    assert tool_schema['properties']['project_id']['description'] == 'Project identifier to list tasks from.'
    assert 'configuration' not in tool_schema['properties']
    assert result.is_error is False
    assert result.structured_content == {'tasks': [{'project_id': 'PB-1', 'workspace': 'Acme', 'title': 'Prepare launch'}]}

@pytest.mark.asyncio
async def test_mcp_list_tools_exposes_declared_output_schemas_and_omits_absent() -> None:
    plugin_api = import_module('umbod_sdk.connectors.plugin_api')
    (configuration_store, publishing_store, runtime) = await _published_project_board_context_for_plugin(_project_board_connector(plugin_api, variant='output_states'))
    mcp = await build_test_mcp(None, None, connector_registrations=runtime.connector_registrations, connector_configuration_store=configuration_store, connector_publishing_store=publishing_store, connector_tool_mappings=runtime.connector_tool_mappings)
    async with Client(mcp) as client:
        tools = {tool.name: tool for tool in await client.list_tools()}
    assert tools['project_board_list_tasks'].output_schema == {'type': 'object', 'properties': {'tasks': {'type': 'array'}}}
    assert tools['project_board_anything'].output_schema == {}
    assert tools['project_board_undeclared'].output_schema is None

def test_tool_output_schema_declaration_reaches_registration_and_preserves_empty_schema() -> None:
    plugin_api = import_module('umbod_sdk.connectors.plugin_api')
    plugin = _project_board_connector(plugin_api, variant='output_states')
    descriptions = plugin.registration()['tool_descriptions']
    assert descriptions[0]['output_schema_status'] == 'present'
    assert descriptions[0]['output_schema'] == {'type': 'object', 'properties': {'tasks': {'type': 'array'}}}
    assert descriptions[1]['output_schema_status'] == 'present'
    assert descriptions[1]['output_schema'] == {}
    assert descriptions[2]['output_schema_status'] == 'absent'
    assert 'output_schema' not in descriptions[2]

def test_tool_decorator_rejects_invalid_json_schema() -> None:
    plugin_api = import_module('umbod_sdk.connectors.plugin_api')
    plugin = _project_board_connector(plugin_api, variant='without_tool')

    @plugin.tool(description='Invalid schema.', output_schema={'type': 'unknown'})
    def invalid_schema() -> dict[str, str]:
        return {}
    with pytest.raises(SchemaError, match='unknown'):
        plugin.registration()

def test_tool_decorator_rejects_unknown_option() -> None:
    plugin_api = import_module('umbod_sdk.connectors.plugin_api')
    plugin = _project_board_connector(plugin_api, variant='without_tool')
    with pytest.raises(TypeError, match="unexpected keyword argument 'unknown_option'"):

        @plugin.tool(description='Invalid option.', unknown_option=True)
        def invalid_option() -> dict[str, str]:
            return {}

@pytest.mark.asyncio
async def test_hidden_configuration_parameter_is_injected_and_excluded_from_mapping_schema() -> None:
    plugin_api = import_module('umbod_sdk.connectors.plugin_api')
    configuration_store = InMemoryConnectorCurrentConfigurationStore()
    await configuration_store.save_current_configuration('project_board', ProjectBoardConfiguration(workspace_name='Acme', api_token=SecretStr('pb-valid')))
    plugin = _project_board_connector(plugin_api)
    mapping = connector_tool_mappings(plugin.definition(), tool_name_prefix='project_board', configuration_store=configuration_store)[0]
    result = await mapping.operation('PB-1')
    assert 'configuration' not in mapping.parameters['properties']
    assert result == {'tasks': [{'project_id': 'PB-1', 'workspace': 'Acme', 'title': 'Prepare launch'}]}

@pytest.mark.asyncio
async def test_async_decorated_connector_function_is_available_as_published_mcp_tool() -> None:
    plugin_api = import_module('umbod_sdk.connectors.plugin_api')
    plugin = _project_board_connector(plugin_api, variant='async_list')
    (configuration_store, publishing_store, runtime) = await _published_project_board_context_for_plugin(plugin)
    mcp = await build_test_mcp(None, None, connector_registrations=runtime.connector_registrations, connector_configuration_store=configuration_store, connector_publishing_store=publishing_store, connector_tool_mappings=runtime.connector_tool_mappings)
    async with Client(mcp) as client:
        tools = await client.list_tools()
        result = await client.call_tool('project_board_list_tasks', {'project_id': 'PB-1'})
    tools_by_name = {tool.name: tool for tool in tools}
    tool_schema = tools_by_name['project_board_list_tasks'].input_schema
    assert tools_by_name['project_board_list_tasks'].description == 'List tasks asynchronously in a Project Board project.'
    assert tool_schema['properties']['project_id']['description'] == 'Project identifier to list tasks from.'
    assert 'configuration' not in tool_schema['properties']
    assert result.is_error is False
    assert result.structured_content == {'tasks': [{'project_id': 'PB-1', 'workspace': 'Acme', 'title': 'Prepare async launch'}]}

@pytest.mark.asyncio
async def test_async_hidden_configuration_parameter_is_injected_and_excluded_from_mapping_schema() -> None:
    plugin_api = import_module('umbod_sdk.connectors.plugin_api')
    configuration_store = InMemoryConnectorCurrentConfigurationStore()
    await configuration_store.save_current_configuration('project_board', ProjectBoardConfiguration(workspace_name='Acme', api_token=SecretStr('pb-valid')))
    plugin = _project_board_connector(plugin_api, variant='async_list')
    mapping = connector_tool_mappings(plugin.definition(), tool_name_prefix='project_board', configuration_store=configuration_store)[0]
    result = mapping.operation('PB-1')
    assert isawaitable(result)
    assert 'configuration' not in mapping.parameters['properties']
    assert await result == {'tasks': [{'project_id': 'PB-1', 'workspace': 'Acme', 'title': 'Prepare async launch'}]}

@pytest.mark.asyncio
async def test_async_connector_tool_failure_is_returned_as_mcp_error_result() -> None:
    plugin_api = import_module('umbod_sdk.connectors.plugin_api')
    plugin = _project_board_connector(plugin_api, variant='async_failing')
    (configuration_store, publishing_store, runtime) = await _published_project_board_context_for_plugin(plugin)
    mcp = await build_test_mcp(None, None, connector_registrations=runtime.connector_registrations, connector_configuration_store=configuration_store, connector_publishing_store=publishing_store, connector_tool_mappings=runtime.connector_tool_mappings)
    async with Client(mcp) as client:
        result = await client.call_tool('project_board_sync_remote_state', {'project_id': 'PB-1'}, raise_on_error=False)
    assert result.is_error is True
    assert 'The Project Board sync_remote_state tool could not complete: remote Project Board unavailable' in result.content[0].text

def test_tool_metadata_can_be_generated_from_pydantic_field_descriptions() -> None:
    plugin_api = import_module('umbod_sdk.connectors.plugin_api')
    plugin = _project_board_connector(plugin_api, variant='search')
    mapping = connector_tool_mappings(plugin.definition(), tool_name_prefix='project_board', configuration_store=InMemoryConnectorCurrentConfigurationStore())[0]
    request_schema = mapping.parameters['properties']['request']
    request_definitions = request_schema['$defs']['SearchTasksRequest']['properties']
    assert mapping.description == 'Search Project Board tasks.'
    assert request_schema['description'] == 'Search task parameters.'
    assert request_definitions['project_id']['description'] == 'Project identifier to search within.'

def test_tool_decorator_metadata_overrides_generated_metadata() -> None:
    plugin_api = import_module('umbod_sdk.connectors.plugin_api')
    plugin = _project_board_connector(plugin_api, variant='find')
    mapping = connector_tool_mappings(plugin.definition(), tool_name_prefix='project_board', configuration_store=InMemoryConnectorCurrentConfigurationStore())[0]
    assert mapping.operation_name == 'find_tasks'
    assert mapping.description == 'Find Project Board tasks with explicit metadata.'
    assert mapping.parameters['properties']['query']['description'] == 'Search text used to match task titles.'

@pytest.mark.parametrize('connector_kind,expected_error', [('invalid_configuration_schema', 'configuration schema'), ('without_configuration_check', 'configuration check')])
def test_connector_registration_validation_rejects_invalid_definitions(connector_kind: str, expected_error: str) -> None:
    plugin_api = import_module('umbod_sdk.connectors.plugin_api')
    connector = _invalid_connector_factories(plugin_api)[connector_kind]
    with pytest.raises(ValueError, match=expected_error):
        connector.registration()

@pytest.mark.parametrize('connector_factory,expected_error', [('without_tool', 'at least one'), ('without_parameter_description', 'project_id')])
def test_connector_tool_documentation_is_required(connector_factory: str, expected_error: str) -> None:
    plugin_api = import_module('umbod_sdk.connectors.plugin_api')
    connector = _undocumented_connector_factories(plugin_api)[connector_factory]
    with pytest.raises(ValueError, match=expected_error):
        connector.registration()

def test_plugin_folder_defaults_to_plugins_connectors_relative_to_working_directory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    plugin_dir = tmp_path / 'plugins' / 'connectors'
    plugin_dir.mkdir(parents=True)
    _write_folder_connector(plugin_dir / 'project_board.py')
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv('UMBOD_CONNECTOR_PLUGIN_DIR', raising=False)
    plugins = load_connector_plugins(False)
    assert 'project_board' in [plugin.registration()['id'] for plugin in plugins]

def test_plugin_folder_can_be_configured_with_environment_variable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    plugin_dir = tmp_path / 'mounted-connectors'
    plugin_dir.mkdir()
    _write_folder_connector(plugin_dir / 'project_board.py')
    monkeypatch.setenv('UMBOD_CONNECTOR_PLUGIN_DIR', str(plugin_dir))
    plugins = load_connector_plugins(False)
    assert 'project_board' in [plugin.registration()['id'] for plugin in plugins]

def test_invalid_plugin_file_does_not_prevent_valid_plugin_from_loading(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    plugin_dir = tmp_path / 'mounted-connectors'
    plugin_dir.mkdir()
    _write_folder_connector(plugin_dir / 'project_board.py')
    (plugin_dir / 'broken.py').write_text("raise RuntimeError('broken plugin')", encoding='utf-8')
    monkeypatch.setenv('UMBOD_CONNECTOR_PLUGIN_DIR', str(plugin_dir))
    discovery_result = load_connector_plugins(include_diagnostics=True)
    assert 'project_board' in [plugin.registration()['id'] for plugin in discovery_result.plugins]
    assert any(('broken' in diagnostic.source for diagnostic in discovery_result.diagnostics))

def _project_board_connector(plugin_api: Any, variant: str='list') -> Any:
    connector = plugin_api.Connector(id='project_board', name='Project Board', description='Connects to Project Board tasks and comments.', capability_description='Search and manage Project Board tasks and comments.', configuration=ProjectBoardConfiguration)

    @connector.configuration_check
    def check_configuration(configuration: ProjectBoardConfiguration) -> Any:
        return plugin_api.ConfigurationCheckResult.valid()
    if variant == 'without_tool':
        pass
    elif variant == 'async_list':

        @connector.tool(description='List tasks asynchronously in a Project Board project.')
        async def list_tasks(project_id: str=Field(description='Project identifier to list tasks from.'), configuration: ProjectBoardConfiguration | None=None) -> dict[str, list[dict[str, str]]]:
            workspace = configuration.workspace_name if configuration is not None else 'unknown'
            return {'tasks': [{'project_id': project_id, 'workspace': workspace, 'title': 'Prepare async launch'}]}
    elif variant == 'async_failing':

        @connector.tool(description='Synchronize remote Project Board state.')
        async def sync_remote_state(project_id: str=Field(description='Project identifier to synchronize.')) -> dict[str, str]:
            raise RuntimeError('remote Project Board unavailable')
    elif variant == 'output_states':

        @connector.tool(description='List tasks with a declared output.', output_schema={'type': 'object', 'properties': {'tasks': {'type': 'array'}}})
        def list_tasks() -> dict[str, list[str]]:
            return {'tasks': []}

        @connector.tool(description='Return anything.', output_schema={})
        def anything() -> dict[str, str]:
            return {}

        @connector.tool(description='Return an undeclared output.')
        def undeclared() -> dict[str, str]:
            return {}
    elif variant == 'search':

        @connector.tool(description='Search Project Board tasks.')
        def search_tasks(request: SearchTasksRequest) -> dict[str, list[str]]:
            return {'matches': [request.query]}
    elif variant == 'find':

        @connector.tool(name='find_tasks', description='Find Project Board tasks with explicit metadata.', parameters={'query': 'Search text used to match task titles.'})
        def search_tasks(query: str=Field(description='Generated query description.')) -> dict[str, list[str]]:
            return {'matches': [query]}
    else:

        @connector.tool(description='List tasks in a Project Board project.')
        def list_tasks(project_id: str=Field(description='Project identifier to list tasks from.'), configuration: ProjectBoardConfiguration | None=None) -> dict[str, list[dict[str, str]]]:
            workspace = configuration.workspace_name if configuration is not None else 'unknown'
            return {'tasks': [{'project_id': project_id, 'workspace': workspace, 'title': 'Prepare launch'}]}
    return connector

def _undocumented_connector_factories(plugin_api: Any) -> dict[str, Any]:
    without_tool = _project_board_connector(plugin_api, variant='without_tool')
    without_parameter_description = _project_board_connector(plugin_api, variant='without_tool')

    @without_parameter_description.tool(description='List tasks in a Project Board project.')
    def list_tasks_without_parameter_description(project_id: str) -> dict[str, list[str]]:
        return {'tasks': [project_id]}
    return {'without_tool': without_tool, 'without_parameter_description': without_parameter_description}

def _invalid_connector_factories(plugin_api: Any) -> dict[str, Any]:
    return {'invalid_configuration_schema': plugin_api.Connector(id='project_board', name='Project Board', description='Connects.', capability_description='Manage Project Board tasks.', configuration=str), 'without_configuration_check': plugin_api.Connector(id='project_board', name='Project Board', description='Connects to Project Board tasks and comments.', capability_description='Manage Project Board tasks and comments.', configuration=ProjectBoardConfiguration)}

async def _published_project_board_context_for_plugin(plugin: Any) -> tuple[Any, Any, Any]:
    configuration_store = InMemoryConnectorCurrentConfigurationStore()
    publishing_store = ConnectorPublishingStoreService(create_inmemory_runtime().database, PUBLICATION_STATE_TABLE)
    await configuration_store.save_current_configuration('project_board', ProjectBoardConfiguration(workspace_name='Acme', api_token=SecretStr('pb-valid')))
    await publishing_store.publish_connector('project_board')
    runtime = assemble_connector_runtime(plugins=[plugin], availability=DeploymentConnectorAvailability.from_mapping({'connectors': [{'id': 'project_board'}]}), configuration_store=configuration_store, publishing_store=publishing_store)
    return (configuration_store, publishing_store, runtime)

def _write_folder_connector(path: Path) -> None:
    path.write_text('\n'.join(['from pydantic import ConfigDict, Field, SecretStr', 'from umbod_sdk.connectors.proxies import Model', 'from umbod_sdk.connectors.plugin_api import ConfigurationCheckResult, Connector', '', 'class ProjectBoardConfiguration(Model):', "    model_config = ConfigDict(extra='forbid')", "    workspace_name: str = Field(description='Workspace name shown to Umbod administrators.')", "    api_token: SecretStr = Field(description='API token used to connect to Project Board.')", '', "plugin = Connector(id='project_board', name='Project Board', description='Connects to Project Board tasks and comments.', capability_description='Search and manage Project Board tasks and comments.', configuration=ProjectBoardConfiguration)", '', '@plugin.configuration_check', 'def check_configuration(configuration: ProjectBoardConfiguration) -> ConfigurationCheckResult:', '    return ConfigurationCheckResult.valid()', '', "@plugin.tool(description='List tasks in a Project Board project.')", "def list_tasks(project_id: str = Field(description='Project identifier to list tasks from.')) -> dict[str, list[str]]:", "    return {'tasks': [project_id]}"]), encoding='utf-8')
