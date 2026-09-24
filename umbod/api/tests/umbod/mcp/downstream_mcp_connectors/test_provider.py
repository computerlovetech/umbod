from umbod.core.configuration.persistence import AuthenticatedTextCipher
from umbod.core.publishing.stores.schema import PUBLICATION_STATE_TABLE
from umbod.core.publishing.stores.service import ConnectorPublishingStoreService
from umbod.core.activation import ActivationStatus, CapabilityRef, create_capability_activation_store
from umbod.core.connectors.downstream_mcp.stores import CONNECTOR_CREDENTIAL_TABLE, CONNECTOR_DEFINITION_TABLE, ConnectorDefinitionStoreService, EncryptedCredentialStoreService, TOOL_CATALOG_TABLE, ToolCatalogStoreService
from tests.persistence_runtime import create_inmemory_runtime
import asyncio
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from types import SimpleNamespace
import pytest
from umbod.core.invocation import ConnectorInvocation, ConnectorInvocationDenied, ConnectorInvocationPolicy, PermitAllConnectorInvocationPolicy
from umbod.core.capabilities.descriptions import SystemConnectorCapabilityDescriptionOverrideStore
from umbod.core.connectors.downstream_mcp.models import DiscoveredPrompt, DiscoveredResource, DiscoveredResourceTemplate, DiscoveredToolWithOutputSchema, NoAuthConnectorDefinition, NoAuthCredentialState, PromptArgument, ToolCatalogSnapshot, ToolIdentity
from umbod.core.connectors.downstream_mcp.stores import ConnectorIdQuery, ReplaceToolCatalog, SaveConnectorDefinition, SaveCredential, ToolCatalogFound
from umbod.core.connectors.downstream_mcp.probe import DiscoverDownstreamTools
from umbod.core.permissions import ConnectorCapabilityPermission, ConnectorToolPermission, InMemoryGroupConnectorToolPermissions
from umbod.mcp.connectors import ModernConnectorApprovalRequired
from umbod.mcp.downstream_mcp_connectors import ConnectorAwareDownstreamMcpToolProvider, GroupDownstreamToolPermissionPolicy, NativeCapabilityProviderView, UnrestrictedDownstreamToolPermissionPolicy
from umbod.mcp.logging import ConnectorToolInvocationLogger, McpAuditEvent, McpAuditRecorder, McpToolInvocationCompleted, create_default_connector_tool_invocation_logger
from umbod.mcp.logging.audit.formatting import StructuredMcpAuditFormatter
from umbod.mcp.logging.invocation.formatting import StructuredMcpToolInvocationLogFormatter
from umbod.mcp.logging.invocation.sink import InMemoryMcpToolInvocationLogSink
from umbod.mcp.metrics import InMemoryMcpMetricsRecorder
from fastmcp import Client, FastMCP
from fastmcp.tools import InputRequiredToolResult, ToolResult
from mcp.types import Icon, InputRequiredResult, TextContent, ToolAnnotations

class RecordingInvocationPolicy:

    def __init__(self, events: list[str], failure: BaseException | None=None) -> None:
        self.events = events
        self.failure = failure
        self.invocations: list[ConnectorInvocation] = []

    async def evaluate(self, invocation: ConnectorInvocation) -> None:
        self.events.append('policy')
        self.invocations.append(invocation)
        if self.failure is not None:
            raise self.failure

class NullToolInvocationLogger:

    def record_tool_invocation_completed(self, event: McpToolInvocationCompleted) -> None:
        return None

@dataclass(frozen=True)
class ProviderOptions:
    display_names: dict[str, str] | None
    tool_invocation_logger: ConnectorToolInvocationLogger | None

class RecordingAuditSink:

    def __init__(self) -> None:
        self.events: list[McpAuditEvent] = []

    def record_mcp_activity(self, event: McpAuditEvent) -> None:
        self.events.append(event)

class InMemoryServerClientFactory:

    def __init__(self, servers: dict[str, FastMCP]) -> None:
        self._servers = servers
        self.created: list[str] = []

    def create(self, command: DiscoverDownstreamTools) -> Client:
        connector_id = command.definition.connector_id
        self.created.append(connector_id)
        return Client(self._servers[connector_id])

async def _provider(servers: dict[str, FastMCP], options: ProviderOptions=ProviderOptions(None, None), invocation_policy: ConnectorInvocationPolicy=PermitAllConnectorInvocationPolicy()) -> tuple[ConnectorAwareDownstreamMcpToolProvider, InMemoryServerClientFactory, ConnectorPublishingStoreService, ToolCatalogStoreService]:
    database = create_inmemory_runtime().database
    definitions = ConnectorDefinitionStoreService(database, CONNECTOR_DEFINITION_TABLE)
    credentials = EncryptedCredentialStoreService(database, CONNECTOR_CREDENTIAL_TABLE, AuthenticatedTextCipher('test-key'))
    catalogs = ToolCatalogStoreService(database, TOOL_CATALOG_TABLE)
    publishing = ConnectorPublishingStoreService(database, PUBLICATION_STATE_TABLE)
    activations = await create_capability_activation_store(database)
    factory = InMemoryServerClientFactory(servers)
    for connector_id in servers:
        await definitions.save(SaveConnectorDefinition(definition=NoAuthConnectorDefinition(connector_id=connector_id, display_name=(options.display_names or {}).get(connector_id, connector_id), capability_description=f'Manage {connector_id} forecasts', endpoint_url=f'https://{connector_id}.example/mcp')))
        await credentials.save(SaveCredential(credential=NoAuthCredentialState(connector_id=connector_id)))
        await catalogs.replace(ReplaceToolCatalog(snapshot=ToolCatalogSnapshot(connector_id=connector_id, discovered_at=datetime(2026, 1, 1, tzinfo=UTC), prompts=(DiscoveredPrompt(name='weather_prompt', title='Weather prompt', description='Build a weather prompt', arguments=(PromptArgument(name='city', required=True),)),), resources=(DiscoveredResource(name='weather', title='Weather', uri=f'data://{connector_id}/weather', description='Current weather'),), resource_templates=(DiscoveredResourceTemplate(name='weather_city', title='Weather city', uri_template=f'data://{connector_id}/{{city}}', description='Weather by city'),), tools=(DiscoveredToolWithOutputSchema(identity=ToolIdentity(connector_id=connector_id, downstream_name='forecast'), title='Forecast', description='Detailed forecast', input_schema={'type': 'object', 'properties': {'city': {'type': 'string'}}, 'required': ['city']}, output_schema={'type': 'object'}, annotations={'readOnlyHint': True}, icons=({'src': 'https://example.test/icon.png', 'mimeType': 'image/png'},), meta={'vendor': 'weather'}, execution={'taskSupport': 'optional'}),))))
        await publishing.publish_connector(connector_id)
        await activations.set_status(CapabilityRef(connector_kind="downstream_mcp", connector_id=connector_id, capability_kind="tool", capability_key='forecast'), ActivationStatus.ENABLED)
        await activations.set_status(CapabilityRef(connector_kind="downstream_mcp", connector_id=connector_id, capability_kind="prompt", capability_key='weather_prompt'), ActivationStatus.ENABLED)
        await activations.set_status(CapabilityRef(connector_kind="downstream_mcp", connector_id=connector_id, capability_kind="resource", capability_key=f'data://{connector_id}/weather'), ActivationStatus.ENABLED)
        await activations.set_status(CapabilityRef(connector_kind="downstream_mcp", connector_id=connector_id, capability_kind="resource_template", capability_key=f'data://{connector_id}/{{city}}'), ActivationStatus.ENABLED)
    return (ConnectorAwareDownstreamMcpToolProvider(definitions=definitions, credentials=credentials, catalogs=catalogs, publishing=publishing, activations=activations, client_factory=factory, permission_policy=UnrestrictedDownstreamToolPermissionPolicy(), connector_scope='', capability_description_overrides=SystemConnectorCapabilityDescriptionOverrideStore(), tool_invocation_logger=options.tool_invocation_logger or NullToolInvocationLogger(), metrics_recorder=InMemoryMcpMetricsRecorder(), invocation_policy=invocation_policy), factory, publishing, activations, catalogs)

def _downstream(calls: list[str] | None=None, *, is_error: bool=False) -> FastMCP:
    server = FastMCP('downstream')

    @server.tool(name='forecast', annotations=ToolAnnotations(readOnlyHint=True), icons=[Icon(src='https://example.test/icon.png', mimeType='image/png')])
    async def forecast(city: str) -> ToolResult:
        if calls is not None:
            calls.append(city)
        await asyncio.sleep(0)
        return ToolResult(content=[TextContent(type='text', text=city, annotations=None, _meta=None)], structured_content={'city': city}, meta={'response': 'unchanged'}, is_error=is_error)

    @server.resource('data://weather/weather')
    def weather_resource() -> str:
        return 'weather'

    @server.resource('data://weather/{city}')
    def weather_city(city: str) -> str:
        return city

    @server.prompt(name='weather_prompt')
    def weather_prompt(city: str) -> str:
        return city
    return server

@pytest.mark.asyncio
@pytest.mark.parametrize('exposure', ['flat', 'gateway'])
async def test_permitted_downstream_invocation_evaluates_canonical_context_before_one_tools_call(exposure: str) -> None:
    events: list[str] = []
    calls: list[str] = []
    policy = RecordingInvocationPolicy(events)
    (provider, _, _, _, _) = await _provider({'weather': _downstream(calls)}, invocation_policy=policy)
    if exposure == 'flat':
        public = FastMCP('public', providers=[provider])
        async with Client(public) as client:
            result = await client.call_tool_mcp('weather_forecast', {'city': 'Copenhagen'})
    else:
        public = FastMCP('public')

        @public.tool(name='execute_tool')
        async def execute_tool() -> ToolResult:
            return await provider.execute_tool('weather_forecast', {'city': 'Copenhagen'})
        async with Client(public) as client:
            result = await client.call_tool_mcp('execute_tool', {})
    assert result.structured_content == {'city': 'Copenhagen'}
    assert events == ['policy']
    assert calls == ['Copenhagen']
    assert policy.invocations == [ConnectorInvocation.create(connector_kind='downstream_mcp', connector_id='weather', operation_name='forecast', public_tool_name='weather_forecast', arguments={'city': 'Copenhagen'})]

@pytest.mark.asyncio
async def test_denied_downstream_invocation_skips_tools_call_and_hides_rationale() -> None:
    events: list[str] = []
    calls: list[str] = []
    policy = RecordingInvocationPolicy(events, ConnectorInvocationDenied('private rationale'))
    (provider, _, _, _, _) = await _provider({'weather': _downstream(calls)}, invocation_policy=policy)
    public = FastMCP('public', providers=[provider])
    async with Client(public) as client:
        result = await client.call_tool_mcp('weather_forecast', {'city': 'Copenhagen'})
    assert result.is_error is True
    assert 'private rationale' not in result.content[0].text
    assert events == ['policy']
    assert len(policy.invocations) == 1
    assert calls == []

@pytest.mark.asyncio
async def test_modern_downstream_approval_returns_input_required_result() -> None:
    events: list[str] = []
    calls: list[str] = []
    invocation = ConnectorInvocation.create(connector_kind='downstream_mcp', connector_id='weather', operation_name='forecast', public_tool_name='weather_forecast', arguments={'city': 'Copenhagen'})
    approval_result = InputRequiredToolResult(InputRequiredResult(inputRequests={}, requestState='sealed'))
    approval = ModernConnectorApprovalRequired(invocation, 1, approval_result)
    policy = RecordingInvocationPolicy(events, approval)
    (provider, _, _, _, _) = await _provider({'weather': _downstream(calls)}, invocation_policy=policy)
    result = await provider.execute_tool('weather_forecast', {'city': 'Copenhagen'})
    assert result is approval_result
    assert events == ['policy']
    assert calls == []

@pytest.mark.asyncio
async def test_unexpected_downstream_policy_failure_hides_canary_without_tools_call() -> None:
    canary = 'policy-canary-secret'
    events: list[str] = []
    calls: list[str] = []
    policy = RecordingInvocationPolicy(events, RuntimeError(canary))
    (provider, _, _, _, _) = await _provider({'weather': _downstream(calls)}, invocation_policy=policy)
    public = FastMCP('public', providers=[provider])
    async with Client(public) as client:
        result = await client.call_tool_mcp('weather_forecast', {'city': 'Copenhagen'})
    assert result.is_error is True
    assert canary not in result.content[0].text
    assert events == ['policy']
    assert calls == []

@pytest.mark.asyncio
async def test_invalid_downstream_arguments_skip_policy_and_tools_call() -> None:
    events: list[str] = []
    calls: list[str] = []
    policy = RecordingInvocationPolicy(events)
    (provider, _, _, _, _) = await _provider({'weather': _downstream(calls)}, invocation_policy=policy)
    with pytest.raises(Exception):
        await provider.execute_tool('weather_forecast', {'city': 42})
    assert events == []
    assert calls == []

@pytest.mark.asyncio
async def test_unknown_downstream_tool_skips_policy_and_tools_call() -> None:
    events: list[str] = []
    calls: list[str] = []
    policy = RecordingInvocationPolicy(events)
    (provider, _, _, _, _) = await _provider({'weather': _downstream(calls)}, invocation_policy=policy)
    with pytest.raises(Exception, match='Unknown tool'):
        await provider.execute_tool('weather_unknown', {'city': 'Copenhagen'})
    assert policy.invocations == []
    assert calls == []

@pytest.mark.asyncio
async def test_downstream_policy_cancellation_propagates_without_tools_call() -> None:
    events: list[str] = []
    calls: list[str] = []
    policy = RecordingInvocationPolicy(events, asyncio.CancelledError())
    (provider, _, _, _, _) = await _provider({'weather': _downstream(calls)}, invocation_policy=policy)
    with pytest.raises(asyncio.CancelledError):
        await provider.execute_tool('weather_forecast', {'city': 'Copenhagen'})
    assert events == ['policy']
    assert calls == []

@pytest.mark.asyncio
async def test_listing_downstream_tools_skips_invocation_policy() -> None:
    events: list[str] = []
    policy = RecordingInvocationPolicy(events)
    (provider, _, _, _, _) = await _provider({'weather': _downstream()}, invocation_policy=policy)
    await provider.list_tools()
    await provider.eligible_search_candidates()
    assert policy.invocations == []
    assert events == []

@pytest.mark.asyncio
async def test_list_uses_persisted_catalog_without_contacting_downstream() -> None:
    (provider, factory, _, _, _) = await _provider({'weather': _downstream()})
    tools = await provider.list_tools()
    assert factory.created == []
    assert [tool.name for tool in tools] == ['weather_forecast']
    tool = tools[0]
    assert tool.description == 'Detailed forecast'
    assert tool.parameters['required'] == ['city']
    assert tool.output_schema == {'type': 'object'}
    assert tool.annotations.read_only_hint is True
    assert str(tool.icons[0].src) == 'https://example.test/icon.png'
    assert tool.meta == {'vendor': 'weather'}
    assert tool.execution.task_support == 'optional'

@pytest.mark.asyncio
async def test_gateway_candidates_use_persisted_catalog_without_contacting_downstream() -> None:
    (provider, factory, _, _, _) = await _provider({'weather': _downstream()})
    candidates = await provider.eligible_search_candidates()
    assert factory.created == []
    assert [candidate.tool_name for candidate in candidates] == ['weather_forecast']
    assert candidates[0].description == 'Detailed forecast'
    assert candidates[0].connector_capability_description == 'Manage weather forecasts'
    assert candidates[0].input_schema['required'] == ['city']

@pytest.mark.asyncio
async def test_gateway_execution_delegates_to_authorized_proxy() -> None:
    (provider, factory, _, _, _) = await _provider({'weather': _downstream()})
    public = FastMCP('public')

    @public.tool(name='execute_tool')
    async def execute_tool() -> ToolResult:
        return await provider.execute_tool('weather_forecast', {'city': 'Copenhagen'})
    async with Client(public) as client:
        result = await client.call_tool_mcp('execute_tool', {})
    assert factory.created == ['weather']
    assert result.structured_content == {'city': 'Copenhagen'}
    assert result.is_error is False

@pytest.mark.asyncio
async def test_fastmcp_exposes_only_namespaced_tools_and_preserves_result() -> None:
    (provider, _, _, _, _) = await _provider({'weather': _downstream()})
    public = FastMCP('public', providers=[provider])
    async with Client(public) as client:
        tools = await client.list_tools()
        resources = await client.list_resources()
        prompts = await client.list_prompts()
        result = await client.call_tool_mcp('weather_forecast', {'city': 'Copenhagen'})
    assert [tool.name for tool in tools] == ['weather_forecast']
    assert [str(resource.uri) for resource in resources] == ['data://weather/weather']
    assert [prompt.name for prompt in prompts] == ['weather_weather_prompt']
    assert result.content[0].text == 'Copenhagen'
    assert result.structured_content == {'city': 'Copenhagen'}
    assert result.is_error is False
    assert result.meta is not None
    assert result.meta['response'] == 'unchanged'
    assert result.meta['io.modelcontextprotocol/serverInfo']['name'] == 'downstream'

@pytest.mark.asyncio
async def test_fastmcp_forwards_prompt_arguments_and_resource_reads() -> None:
    (provider, factory, _, _, _) = await _provider({'weather': _downstream()})
    public = FastMCP('public', providers=[provider])
    async with Client(public) as client:
        templates = await client.list_resource_templates()
        prompt = await client.get_prompt('weather_weather_prompt', {'city': 'Copenhagen'})
        fixed = await client.read_resource('data://weather/weather')
        templated = await client.read_resource('data://weather/Copenhagen')
    assert [template.uri_template for template in templates] == ['data://weather/{city}']
    assert prompt.messages[0].content.text == 'Copenhagen'
    assert fixed[0].text == 'weather'
    assert templated[0].text == 'Copenhagen'
    assert factory.created == ['weather', 'weather', 'weather']

@pytest.mark.asyncio
async def test_prompt_and_resources_require_publication_and_activation(monkeypatch: pytest.MonkeyPatch) -> None:
    (provider, _, publishing, activations, _) = await _provider({'weather': _downstream()})
    permissions = InMemoryGroupConnectorToolPermissions(group_claim_fields=('groups',))
    permissions.replace_group_permissions(
        {'support': ('weather',)},
        {
            'support': (
                ConnectorCapabilityPermission('weather', 'prompt', 'weather_prompt'),
                ConnectorCapabilityPermission('weather', 'resource', 'data://weather/weather'),
                ConnectorCapabilityPermission(
                    'weather', 'resource_template', 'data://weather/{city}'
                ),
            )
        },
    )
    provider._permission_policy = GroupDownstreamToolPermissionPolicy(permissions)
    monkeypatch.setattr('umbod.mcp.downstream_mcp_connectors.provider.get_access_token', lambda : SimpleNamespace(claims={'groups': ['support']}))
    await activations.set_status(CapabilityRef(connector_kind="downstream_mcp", connector_id='weather', capability_kind="tool", capability_key='forecast'), ActivationStatus.DISABLED)
    await activations.set_status(CapabilityRef(connector_kind="downstream_mcp", connector_id='weather', capability_kind="prompt", capability_key='weather_prompt'), ActivationStatus.DISABLED)
    await activations.set_status(CapabilityRef(connector_kind="downstream_mcp", connector_id='weather', capability_kind="resource", capability_key='data://weather/weather'), ActivationStatus.DISABLED)
    await activations.set_status(CapabilityRef(connector_kind="downstream_mcp", connector_id='weather', capability_kind="resource_template", capability_key='data://weather/{city}'), ActivationStatus.DISABLED)
    public = FastMCP('public', providers=[provider])
    async with Client(public) as client:
        assert await client.list_prompts() == []
        assert await client.list_resources() == []
        assert await client.list_resource_templates() == []
        await activations.set_status(CapabilityRef(connector_kind="downstream_mcp", connector_id='weather', capability_kind="prompt", capability_key='weather_prompt'), ActivationStatus.ENABLED)
        await activations.set_status(CapabilityRef(connector_kind="downstream_mcp", connector_id='weather', capability_kind="resource", capability_key='data://weather/weather'), ActivationStatus.ENABLED)
        await activations.set_status(CapabilityRef(connector_kind="downstream_mcp", connector_id='weather', capability_kind="resource_template", capability_key='data://weather/{city}'), ActivationStatus.ENABLED)
        assert [prompt.name for prompt in await client.list_prompts()] == ['weather_weather_prompt']
        assert len(await client.list_resources()) == 1
        assert len(await client.list_resource_templates()) == 1
        await publishing.unpublish_connector('weather')
        assert await client.list_prompts() == []
        assert await client.list_resources() == []
        assert await client.list_resource_templates() == []
        with pytest.raises(Exception, match='Unknown prompt'):
            await client.get_prompt('weather_weather_prompt', {'city': 'Copenhagen'})
        with pytest.raises(Exception, match='Resource not found'):
            await client.read_resource('data://weather/weather')

@pytest.mark.asyncio
async def test_native_capability_view_structurally_hides_tools() -> None:
    (provider, _, _, _, _) = await _provider({'weather': _downstream()})
    public = FastMCP('public', providers=[NativeCapabilityProviderView(provider)])
    async with Client(public) as client:
        assert await client.list_tools() == []
        assert [prompt.name for prompt in await client.list_prompts()] == ['weather_weather_prompt']
        assert len(await client.list_resources()) == 1
        assert len(await client.list_resource_templates()) == 1

@pytest.mark.asyncio
async def test_resource_collisions_withhold_every_owner_and_leave_unrelated_capabilities() -> None:
    (provider, _, _, _, catalogs) = await _provider({'weather': _downstream(), 'calendar': _downstream()})
    for connector_id in ('weather', 'calendar'):
        result = await catalogs.get(ConnectorIdQuery(connector_id=connector_id))
        assert isinstance(result, ToolCatalogFound)
        snapshot = result.snapshot
        await catalogs.replace(ReplaceToolCatalog(snapshot=snapshot.model_copy(update={'resources': (snapshot.resources[0].model_copy(update={'uri': 'data://shared'}),)})))
    resources = await provider.list_resources()
    templates = await provider.list_resource_templates()
    assert resources == []
    assert len(templates) == 2

@pytest.mark.asyncio
async def test_direct_get_materializes_only_target_connector() -> None:
    (provider, factory, _, _, _) = await _provider({'weather': _downstream(), 'calendar': _downstream()})
    tool = await provider.get_tool('weather_forecast')
    assert tool is not None
    public = FastMCP('public', providers=[provider])
    async with Client(public) as client:
        await client.call_tool_mcp('weather_forecast', {'city': 'Copenhagen'})
    assert factory.created == ['weather']

@pytest.mark.asyncio
async def test_stale_tool_rechecks_publication_activation_and_catalog() -> None:
    (provider, _, publishing, activations, catalogs) = await _provider({'weather': _downstream()})
    tool = await provider.get_tool('weather_forecast')
    assert tool is not None
    await publishing.unpublish_connector('weather')
    with pytest.raises(Exception, match='not available'):
        await provider.execute_tool('weather_forecast', {'city': 'Copenhagen'})
    await publishing.publish_connector('weather')
    await activations.set_status(CapabilityRef(connector_kind="downstream_mcp", connector_id='weather', capability_kind="tool", capability_key='forecast'), ActivationStatus.DISABLED)
    with pytest.raises(Exception, match='not available'):
        await provider.execute_tool('weather_forecast', {'city': 'Copenhagen'})
    await activations.set_status(CapabilityRef(connector_kind="downstream_mcp", connector_id='weather', capability_kind="tool", capability_key='forecast'), ActivationStatus.ENABLED)
    await catalogs.delete(ConnectorIdQuery(connector_id='weather'))
    with pytest.raises(Exception, match='Unknown tool'):
        await provider.execute_tool('weather_forecast', {'city': 'Copenhagen'})

@pytest.mark.asyncio
async def test_concurrent_calls_create_fresh_connector_clients() -> None:
    (provider, factory, _, _, _) = await _provider({'weather': _downstream()})
    public = FastMCP('public', providers=[provider])
    async with Client(public) as client:
        await asyncio.gather(client.call_tool_mcp('weather_forecast', {'city': 'A'}), client.call_tool_mcp('weather_forecast', {'city': 'B'}))
    assert factory.created == ['weather', 'weather']

@pytest.mark.asyncio
async def test_group_permission_filters_listing_and_denies_direct_lookup_and_stale_call(monkeypatch: pytest.MonkeyPatch) -> None:
    (provider, _, _, _, _) = await _provider({'weather': _downstream()})
    permissions = InMemoryGroupConnectorToolPermissions(group_claim_fields=('groups',))
    permissions.replace_group_permissions({'engineering': ('weather',), 'support': ()}, {'engineering': (ConnectorToolPermission('weather', 'forecast'),), 'support': ()})
    provider._permission_policy = GroupDownstreamToolPermissionPolicy(permissions)
    monkeypatch.setattr('umbod.mcp.downstream_mcp_connectors.provider.get_access_token', lambda : SimpleNamespace(claims={'groups': ['engineering']}))
    stale_tool = await provider.get_tool('weather_forecast')
    assert stale_tool is not None
    public = FastMCP('public', providers=[provider])
    async with Client(public) as client:
        assert [tool.name for tool in await client.list_tools()] == ['weather_forecast']
        result = await client.call_tool_mcp('weather_forecast', {'city': 'Copenhagen'})
        assert result.structured_content == {'city': 'Copenhagen'}
    monkeypatch.setattr('umbod.mcp.downstream_mcp_connectors.provider.get_access_token', lambda : SimpleNamespace(claims={'groups': ['support']}))
    async with Client(public) as client:
        assert await client.list_tools() == []
        denied = await client.call_tool_mcp('weather_forecast', {'city': 'Copenhagen'})
        assert denied.is_error is True
        assert 'Unknown tool' in denied.content[0].text
    assert await provider.get_tool('weather_forecast') is None
    with pytest.raises(Exception, match='not available'):
        await provider.execute_tool('weather_forecast', {'city': 'Copenhagen'})

@pytest.mark.asyncio
async def test_proxy_records_display_name_failure_without_secret_attributes() -> None:
    invocation_sink = InMemoryMcpToolInvocationLogSink(StructuredMcpToolInvocationLogFormatter())
    audit_sink = RecordingAuditSink()
    logger = create_default_connector_tool_invocation_logger(invocation_sink, McpAuditRecorder(audit_sink, 'test'))
    (provider, _, _, _, _) = await _provider({'weather': _downstream(is_error=True)}, ProviderOptions({'weather': 'Weather Service'}, logger))
    secret = 'downstream-secret-marker'
    tool_name = (await provider.list_tools())[0].name
    public = FastMCP('public')

    @public.tool(name='execute_tool')
    async def execute_tool() -> ToolResult:
        return await provider.execute_tool(tool_name, {'city': secret})
    async with Client(public) as client:
        result = await client.call_tool_mcp('execute_tool', {})
    assert result.is_error is True
    attributes = invocation_sink.invocation_records()[0].attributes
    assert attributes['mcp.connector.name'] == 'Weather Service'
    assert attributes['mcp.invocation.outcome'] == 'failure'
    assert audit_sink.events[0].target.connector_name == 'Weather Service'
    assert secret not in json.dumps(attributes)
    assert secret not in json.dumps(StructuredMcpAuditFormatter().format_mcp_activity(audit_sink.events[0]).attributes)

@pytest.mark.asyncio
async def test_proxy_uses_connector_id_when_display_name_is_empty() -> None:
    invocation_sink = InMemoryMcpToolInvocationLogSink(StructuredMcpToolInvocationLogFormatter())
    audit_sink = RecordingAuditSink()
    logger = create_default_connector_tool_invocation_logger(invocation_sink, McpAuditRecorder(audit_sink, 'test'))
    (provider, _, _, _, _) = await _provider({'weather': _downstream()}, ProviderOptions({'weather': '   '}, logger))
    tool_name = (await provider.list_tools())[0].name
    public = FastMCP('public')

    @public.tool(name='execute_tool')
    async def execute_tool() -> ToolResult:
        return await provider.execute_tool(tool_name, {'city': 'Copenhagen'})
    async with Client(public) as client:
        await client.call_tool_mcp('execute_tool', {})
    assert invocation_sink.invocation_records()[0].attributes['mcp.connector.name'] == 'weather'
    assert audit_sink.events[0].target.connector_name == 'weather'
