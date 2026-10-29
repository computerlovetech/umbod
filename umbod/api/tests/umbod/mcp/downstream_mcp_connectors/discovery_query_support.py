from tests.umbod.mcp.downstream_mcp_connectors.discovery_operation_support import empty_personal_discovery
from umbod.mcp.connectors.downstream_mcp.runtime import DownstreamDiscoveryRuntime, DownstreamDiscoveryStores, create_downstream_discovery_runtime
from dataclasses import dataclass
from datetime import UTC, datetime
from unittest.mock import Mock

from tests.persistence_runtime import create_inmemory_runtime
from tests.umbod.mcp.downstream_mcp_connectors.signal_support import invocation_signals
from umbod.core.activation import ActivationStatus, CapabilityRef, create_capability_activation_store
from umbod.core.capabilities.descriptions import SystemConnectorCapabilityDescriptionOverrideStore
from umbod.core.configuration.persistence import AuthenticatedTextCipher
from umbod.core.connectors.downstream_mcp.models import DiscoveredToolWithoutOutputSchema, NoAuthConnectorDefinition, NoAuthCredentialState, ToolCatalogSnapshot, ToolIdentity
from umbod.core.connectors.downstream_mcp.personal_tools import DisabledPersonalToolRuntime
from umbod.core.connectors.downstream_mcp.stores import CONNECTOR_CREDENTIAL_TABLE, CONNECTOR_DEFINITION_TABLE, TOOL_CATALOG_TABLE, ConnectorDefinitionStore, ConnectorDefinitionStoreService, EncryptedCredentialStore, EncryptedCredentialStoreService, ReplaceToolCatalog, SaveConnectorDefinition, SaveCredential, ToolCatalogStore, ToolCatalogStoreService
from umbod.core.invocation import PermitAllConnectorInvocationPolicy
from umbod.core.publishing import ConnectorPublishingStore
from umbod.core.publishing.stores.schema import PUBLICATION_STATE_TABLE
from umbod.core.publishing.stores.service import ConnectorPublishingStoreService
from umbod.mcp.connectors.downstream_mcp import ConnectorAwareDownstreamMcpToolProvider, UnrestrictedDownstreamToolPermissionPolicy
from umbod.mcp.connectors.downstream_mcp.ports import DownstreamClientFactory
from umbod.mcp.metrics import InMemoryMcpMetricsRecorder
from umbod.mcp.signals import SignalToolExecutionPipelineFactory


@dataclass(frozen=True)
class DiscoveryQueryCase:
    provider: ConnectorAwareDownstreamMcpToolProvider
    definitions: Mock
    catalogs: Mock
    credentials: Mock
    publishing: Mock
    clients: Mock
    runtime: DownstreamDiscoveryRuntime


async def discovery_query_case(tool_count: int) -> DiscoveryQueryCase:
    database = create_inmemory_runtime().database
    definitions = ConnectorDefinitionStoreService(database, CONNECTOR_DEFINITION_TABLE)
    credentials = EncryptedCredentialStoreService(database, CONNECTOR_CREDENTIAL_TABLE, AuthenticatedTextCipher("test-key"))
    catalogs = ToolCatalogStoreService(database, TOOL_CATALOG_TABLE)
    publishing = ConnectorPublishingStoreService(database, PUBLICATION_STATE_TABLE)
    activations = await create_capability_activation_store(database)
    await definitions.save(SaveConnectorDefinition(definition=NoAuthConnectorDefinition(connector_id="shared", display_name="Shared", endpoint_url="https://shared.example/mcp")))
    await credentials.save(SaveCredential(credential=NoAuthCredentialState(connector_id="shared")))
    tools = tuple(DiscoveredToolWithoutOutputSchema(identity=ToolIdentity(connector_id="shared", downstream_name=f"tool_{index}"), title=f"Tool {index}", description="Shared tool", input_schema={"type": "object", "properties": {}}) for index in range(tool_count))
    await catalogs.replace(ReplaceToolCatalog(snapshot=ToolCatalogSnapshot(connector_id="shared", discovered_at=datetime(2026, 1, 1, tzinfo=UTC), tools=tools)))
    await publishing.publish_connector("shared")
    for tool in tools:
        await activations.set_status(CapabilityRef(connector_kind="downstream_mcp", connector_id="shared", capability_kind="tool", capability_key=tool.identity.downstream_name), ActivationStatus.ENABLED)
    counted_definitions = Mock(spec=ConnectorDefinitionStore, wraps=definitions)
    counted_catalogs = Mock(spec=ToolCatalogStore, wraps=catalogs)
    counted_credentials = Mock(spec=EncryptedCredentialStore, wraps=credentials)
    counted_publishing = Mock(spec=ConnectorPublishingStore, wraps=publishing)
    clients = Mock(spec=DownstreamClientFactory)
    clients.create.side_effect = AssertionError("Discovery must not contact downstream servers")
    signals = invocation_signals(InMemoryMcpMetricsRecorder())
    discovery_runtime = create_downstream_discovery_runtime(DownstreamDiscoveryStores(definitions=counted_definitions, credentials=counted_credentials, catalogs=counted_catalogs, publishing=counted_publishing, activations=activations, descriptions=SystemConnectorCapabilityDescriptionOverrideStore()))
    await discovery_runtime.reconcile()
    provider = ConnectorAwareDownstreamMcpToolProvider(discovery_runtime=discovery_runtime, personal_discovery=empty_personal_discovery(discovery_runtime), definitions=counted_definitions, credentials=counted_credentials, catalogs=counted_catalogs, publishing=counted_publishing, activations=activations, client_factory=clients, permission_policy=UnrestrictedDownstreamToolPermissionPolicy(), connector_scope="", signals=signals, execution_pipelines=SignalToolExecutionPipelineFactory(signals, PermitAllConnectorInvocationPolicy()), personal_runtime=DisabledPersonalToolRuntime())
    for store in (counted_definitions, counted_catalogs, counted_credentials, counted_publishing):
        store.reset_mock()
    return DiscoveryQueryCase(provider, counted_definitions, counted_catalogs, counted_credentials, counted_publishing, clients, discovery_runtime)
