from umbod.core.configuration.persistence import AuthenticatedTextCipher
from umbod.core.publishing.factories import create_connector_publishing_store
from umbod.core.publishing.stores.schema import PUBLICATION_STATE_TABLE
from umbod.core.publishing.stores.service import ConnectorPublishingStoreService
from umbod.core.activation import CapabilityRef, create_capability_activation_store
from umbod.core.connectors.downstream_mcp.stores import CONNECTOR_CREDENTIAL_TABLE, CONNECTOR_DEFINITION_TABLE, ConnectorDefinitionStoreService, EncryptedCredentialStoreService, TOOL_CATALOG_TABLE, ToolCatalogStoreService
from tests.persistence_runtime import create_inmemory_runtime, create_sqlite_runtime, prepared_sqlite_runtime
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
import pytest
from umbod.config import ConnectorStoreConfig
from umbod.core.configuration import InMemoryConnectorCurrentConfigurationStore
from umbod.core.connectors.native.runtime import ConnectorRuntime
from umbod.core.activation import ActivationStatus
from umbod.core.connectors.downstream_mcp.models import DiscoveredPrompt, DiscoveredResource, DiscoveredResourceTemplate, DiscoveredToolWithOutputSchema, NoAuthConnectorDefinition, NoAuthCredentialState, PromptArgument, ToolCatalogSnapshot, ToolIdentity
from umbod.core.connectors.downstream_mcp.stores import ReplaceToolCatalog, SaveConnectorDefinition, SaveCredential
from umbod.core.connectors.downstream_mcp.probe import DiscoverDownstreamTools
from umbod.mcp.settings import MCPAppSettings, MCPSettings
from fastmcp import Client, FastMCP
from fastmcp.tools import ToolResult
from tests.mcp_fixtures import build_test_mcp
CONNECTOR_ID = '09ee32b6-a502-4493-977f-baaec560596f'
OPERATION_NAME = 'list_vikunja_tasks'
PROXY_TOOL_NAME = f'Vikunja_{OPERATION_NAME}'
PROXY_PROMPT_NAME = f"{CONNECTOR_ID.replace('-', '_')}_task_prompt"
DOWNSTREAM_RESULT = {'tasks': [{'id': 42, 'title': 'Deterministic task'}]}

class DownstreamInvocationRecorder:

    def __init__(self) -> None:
        self.created_connector_ids: list[str] = []
        self.arguments: list[dict[str, Any]] = []
        self.server = FastMCP('vikunja-downstream')
        self.server.tool(name=OPERATION_NAME)(self._list_tasks)
        self.server.prompt(name='task_prompt')(self._task_prompt)
        self.server.resource('data://vikunja/fixed')(self._fixed_resource)
        self.server.resource('data://vikunja/{task_id}')(self._templated_resource)

    def create(self, command: DiscoverDownstreamTools) -> Client:
        self.created_connector_ids.append(command.definition.connector_id)
        return Client(self.server)

    async def _list_tasks(self, project_id: int) -> ToolResult:
        self.arguments.append({'project_id': project_id})
        return ToolResult(structured_content=DOWNSTREAM_RESULT)

    async def _task_prompt(self, project: str) -> str:
        return f'Summarize {project}'

    async def _fixed_resource(self) -> str:
        return 'fixed tasks'

    async def _templated_resource(self, task_id: str) -> str:
        return f'task {task_id}'

async def _persist_downstream_state(database_path: str, input_schema: dict[str, Any] | None=None) -> None:
    await prepared_sqlite_runtime(database_path)
    await ConnectorDefinitionStoreService(create_sqlite_runtime(database_path).database, CONNECTOR_DEFINITION_TABLE).save(SaveConnectorDefinition(definition=NoAuthConnectorDefinition(connector_id=CONNECTOR_ID, display_name='Vikunja', tool_name_prefix='Vikunja', endpoint_url='https://vikunja.example.test/mcp')))
    await EncryptedCredentialStoreService(create_sqlite_runtime(database_path).database, CONNECTOR_CREDENTIAL_TABLE, AuthenticatedTextCipher('test-secret')).save(SaveCredential(credential=NoAuthCredentialState(connector_id=CONNECTOR_ID)))
    await ToolCatalogStoreService(create_sqlite_runtime(database_path).database, TOOL_CATALOG_TABLE).replace(ReplaceToolCatalog(snapshot=ToolCatalogSnapshot(connector_id=CONNECTOR_ID, discovered_at=datetime(2026, 1, 1, tzinfo=UTC), prompts=(DiscoveredPrompt(name='task_prompt', title='Task prompt', description='Summarize a project', arguments=(PromptArgument(name='project', required=True),)),), resources=(DiscoveredResource(name='fixed', title='Fixed tasks', uri='data://vikunja/fixed', description='Fixed tasks'),), resource_templates=(DiscoveredResourceTemplate(name='task', title='Task', uri_template='data://vikunja/{task_id}', description='Task by identifier'),), tools=(DiscoveredToolWithOutputSchema(identity=ToolIdentity(connector_id=CONNECTOR_ID, downstream_name=OPERATION_NAME), title='List Vikunja tasks', description='List tasks from a Vikunja project.', input_schema=input_schema or {'type': 'object', 'properties': {'project_id': {'type': 'integer'}}, 'required': ['project_id']}, output_schema={'type': 'object'}),))))
    database = (await prepared_sqlite_runtime(database_path)).database
    publishing_store = await create_connector_publishing_store(database)
    await publishing_store.publish_connector(CONNECTOR_ID)
    activation_store = await create_capability_activation_store(database)
    await activation_store.set_status(CapabilityRef(connector_kind="downstream_mcp", connector_id=CONNECTOR_ID, capability_kind="tool", capability_key=OPERATION_NAME), ActivationStatus.ENABLED)
    await activation_store.set_status(CapabilityRef(connector_kind="downstream_mcp", connector_id=CONNECTOR_ID, capability_kind="prompt", capability_key="task_prompt"), ActivationStatus.ENABLED)
    await activation_store.set_status(CapabilityRef(connector_kind="downstream_mcp", connector_id=CONNECTOR_ID, capability_kind="resource", capability_key="data://vikunja/fixed"), ActivationStatus.ENABLED)
    await activation_store.set_status(CapabilityRef(connector_kind="downstream_mcp", connector_id=CONNECTOR_ID, capability_kind="resource_template", capability_key="data://vikunja/{task_id}"), ActivationStatus.ENABLED)

async def _build_public_mcp(tmp_path: Path, exposure_mode: str, monkeypatch: pytest.MonkeyPatch, input_schema: dict[str, Any] | None=None) -> tuple[FastMCP, DownstreamInvocationRecorder]:
    database_path = str(tmp_path / f'{exposure_mode}.sqlite3')
    await _persist_downstream_state(database_path, input_schema)
    recorder = DownstreamInvocationRecorder()
    monkeypatch.setattr('umbod.core.connectors.downstream_mcp.adapters.fastmcp.client.FastMCPDownstreamClientFactory.create', recorder.create)
    settings = MCPAppSettings(mcp=MCPSettings(connector_tool_exposure_mode=exposure_mode, downstream_discovery_enabled=False, _env_file=None), connector_store=ConnectorStoreConfig(type='sqlite', sqlite_path=database_path), connector_security={'configuration_secret': 'test-secret'}, _env_file=None)
    connector_runtime = ConnectorRuntime(connector_registrations=[], connector_configuration_store=InMemoryConnectorCurrentConfigurationStore(), connector_publishing_store=ConnectorPublishingStoreService(create_inmemory_runtime().database, PUBLICATION_STATE_TABLE), connector_tool_mappings=[])
    return (await build_test_mcp(settings, connector_runtime=connector_runtime), recorder)

@pytest.mark.asyncio
async def test_flat_exposes_and_invokes_persisted_downstream_proxy_directly(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (mcp, recorder) = await _build_public_mcp(tmp_path, 'flat', monkeypatch)
    async with Client(mcp) as client:
        names = [tool.name for tool in await client.list_tools()]
        assert recorder.created_connector_ids == []
        result = await client.call_tool_mcp(PROXY_TOOL_NAME, {'project_id': 7})
    assert PROXY_TOOL_NAME in names
    assert 'search_tools' not in names
    assert 'execute_tool' not in names
    assert result.structured_content == DOWNSTREAM_RESULT
    assert recorder.created_connector_ids == [CONNECTOR_ID]
    assert recorder.arguments == [{'project_id': 7}]

@pytest.mark.asyncio
@pytest.mark.parametrize('exposure_mode', ['flat', 'gateway', 'codemode'])
async def test_all_exposure_modes_expose_native_capabilities_without_leaking_gateway_tools(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, exposure_mode: str) -> None:
    (mcp, _) = await _build_public_mcp(tmp_path, exposure_mode, monkeypatch)
    async with Client(mcp) as client:
        tool_names = [tool.name for tool in await client.list_tools()]
        prompts = await client.list_prompts()
        prompt = await client.get_prompt(PROXY_PROMPT_NAME, {'project': 'Roadmap'})
        resources = await client.list_resources()
        templates = await client.list_resource_templates()
        fixed = await client.read_resource('data://vikunja/fixed')
        templated = await client.read_resource('data://vikunja/42')
    assert [item.name for item in prompts] == [PROXY_PROMPT_NAME]
    assert prompt.messages[0].content.text == 'Summarize Roadmap'
    assert [str(item.uri) for item in resources] == ['data://vikunja/fixed']
    assert [item.uri_template for item in templates] == ['data://vikunja/{task_id}']
    assert fixed[0].text == 'fixed tasks'
    assert templated[0].text == 'task 42'
    assert (PROXY_TOOL_NAME in tool_names) is (exposure_mode == 'flat')

@pytest.mark.asyncio
async def test_flat_preserves_referenced_object_field_descriptions_for_mcp_clients(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    input_schema = {'type': 'object', 'properties': {'draft': {'$ref': '#/$defs/UpdateVikunjaTaskDraft'}}, 'required': ['draft'], '$defs': {'UpdateVikunjaTaskDraft': {'type': 'object', 'properties': {'task_id': {'type': 'integer', 'description': 'Numeric Vikunja task ID to update.'}, 'title': {'anyOf': [{'type': 'string'}, {'type': 'null'}], 'description': 'New nonempty task title. Omit to leave unchanged.'}}, 'required': ['task_id']}}}
    (mcp, _) = await _build_public_mcp(tmp_path, 'flat', monkeypatch, input_schema)
    async with Client(mcp) as client:
        tools = await client.list_tools()
    proxy_tool = next((tool for tool in tools if tool.name == PROXY_TOOL_NAME))
    draft_schema = proxy_tool.input_schema['properties']['draft']
    assert draft_schema['required'] == ['task_id']
    assert draft_schema['properties']['task_id']['description'] == 'Numeric Vikunja task ID to update.'
    assert draft_schema['properties']['title']['description'] == 'New nonempty task title. Omit to leave unchanged.'

@pytest.mark.asyncio
async def test_gateway_discovers_and_executes_persisted_downstream_proxy(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (mcp, recorder) = await _build_public_mcp(tmp_path, 'gateway', monkeypatch)
    async with Client(mcp) as client:
        names = [tool.name for tool in await client.list_tools()]
        search = await client.call_tool('search_tools', {'query': 'Vikunja tasks', 'connector_ids': ['unknown', CONNECTOR_ID]})
        denied_search = await client.call_tool('search_tools', {'query': 'Vikunja tasks', 'connector_ids': ['unknown']})
        assert recorder.created_connector_ids == []
        result = await client.call_tool('execute_tool', {'tool_name': PROXY_TOOL_NAME, 'arguments': {'project_id': 7}})
    assert PROXY_TOOL_NAME not in names
    assert [match['tool_name'] for match in search.structured_content['matches']] == [PROXY_TOOL_NAME]
    assert denied_search.is_error is False
    assert denied_search.structured_content == {'matches': []}
    assert result.structured_content == DOWNSTREAM_RESULT
    assert recorder.created_connector_ids == [CONNECTOR_ID]
    assert recorder.arguments == [{'project_id': 7}]

@pytest.mark.asyncio
async def test_codemode_discovers_and_executes_persisted_downstream_proxy_from_code(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (mcp, recorder) = await _build_public_mcp(tmp_path, 'codemode', monkeypatch)
    async with Client(mcp) as client:
        names = [tool.name for tool in await client.list_tools()]
        search = await client.call_tool('search_tools', {'query': 'Vikunja tasks'})
        assert recorder.created_connector_ids == []
        result = await client.call_tool('execute_code', {'code': f"{PROXY_TOOL_NAME.replace('-', '_')}(project_id=7)"})
    assert PROXY_TOOL_NAME not in names
    assert [match['tool_name'] for match in search.structured_content['matches']] == [PROXY_TOOL_NAME]
    assert result.structured_content['outcome'] == 'success'
    assert result.structured_content['final_value'] == DOWNSTREAM_RESULT
    assert recorder.created_connector_ids == [CONNECTOR_ID]
    assert recorder.arguments == [{'project_id': 7}]
