import asyncio
from datetime import UTC, datetime

import pytest

from messaging.models import MessagingEvent
from tests.persistence_runtime import create_inmemory_runtime
from umbod.config import AppConfig, McpConfig
from umbod.core.activation import ActivationStatus, CapabilityRef
from umbod.core.callers import GroupMembership
from umbod.core.capabilities.descriptions import ConnectorCapabilityDescriptionKey, SetCapabilityDescriptionOverride
from umbod.core.connectors.downstream_mcp.models import DiscoveredToolWithoutOutputSchema, NoAuthConnectorDefinition, NoAuthCredentialState, ToolCatalogSnapshot, ToolIdentity
from umbod.core.connectors.downstream_mcp.stores import ReplaceToolCatalog, SaveConnectorDefinition, SaveCredential, create_downstream_mcp_stores
from umbod.core.connectors.native.runtime import ConnectorRuntime
from umbod.core.messaging import DatabaseEventStream
from umbod.core.permissions import InMemoryGroupConnectorToolPermissions
from umbod.core.permissions.domain import SaveGroupPermissionsRequest
from umbod.core.permissions.factories import create_group_permission_store
from umbod.mcp.context import PublicAppConfig
from umbod.mcp.public_app import build_starlette_app, create_runtime_context
from umbod.mcp.runtime_options import ConnectorRuntimeSourceStores, StoreBackedConnectorRuntimeStateSourceStrategy


@pytest.mark.asyncio
async def test_http_without_api_url_consumes_durable_permission_description_and_activation_changes() -> None:
    persistence = create_inmemory_runtime()
    await persistence.readiness.ensure_ready()
    settings = AppConfig(mcp=McpConfig(auth_mode='none', messaging_transport='http', metrics_enabled=False, downstream_discovery_enabled=False), connector_security={'configuration_secret': 'test-secret'})
    stores = await create_downstream_mcp_stores('test-secret', persistence.database)
    await stores.definitions.save(SaveConnectorDefinition(definition=NoAuthConnectorDefinition(connector_id='shared', display_name='Shared', endpoint_url='https://example.test/mcp')))
    await stores.credentials.save(SaveCredential(credential=NoAuthCredentialState(connector_id='shared')))
    tool = DiscoveredToolWithoutOutputSchema(identity=ToolIdentity(connector_id='shared', downstream_name='read'), title='Read', description='Read', input_schema={'type': 'object', 'properties': {}})
    await stores.catalogs.replace(ReplaceToolCatalog(snapshot=ToolCatalogSnapshot(connector_id='shared', discovered_at=datetime(2026, 1, 1, tzinfo=UTC), tools=(tool,))))
    await stores.publishing.publish_connector('shared')
    ref = CapabilityRef(connector_kind='downstream_mcp', connector_id='shared', capability_kind='tool', capability_key='read')
    await stores.activations.set_status(ref, ActivationStatus.ENABLED)
    permissions = InMemoryGroupConnectorToolPermissions(group_claim_fields=('groups',))
    runtime = ConnectorRuntime(connector_registrations=[], connector_configuration_store=None, connector_publishing_store=None, connector_tool_mappings=[])
    context = await create_runtime_context(PublicAppConfig(settings=settings, connector_runtime=runtime, source_stores=ConnectorRuntimeSourceStores(), configured_source_strategy=StoreBackedConnectorRuntimeStateSourceStrategy(), stateless_http=True, api_base_url=None, persistence_runtime=persistence, group_permission_runtime_state=permissions))
    app = await build_starlette_app(context)
    health = context.mcp.runtime_projection_health
    assert not health.ready
    async with app.router.lifespan_context(app):
        assert health.ready
        assert len(context.mcp.downstream_mcp_discovery_runtime.capture().available_records) == 1
        membership = GroupMembership(group_ids=('readers',))
        assert permissions.allowed_connector_ids(membership) == set()
        permission_store = await create_group_permission_store(persistence.database)
        await permission_store.save_group_permissions(SaveGroupPermissionsRequest(group_id='readers', connector_ids=('shared',), capabilities=()))
        await context.mcp.capability_description_overrides.set(SetCapabilityDescriptionOverride(key=ConnectorCapabilityDescriptionKey(kind='downstream_mcp', connector_id='shared'), description='Updated shared connector', expected_revision=0))
        await stores.activations.set_status(ref, ActivationStatus.DISABLED)
        stream = DatabaseEventStream(persistence.database)
        await stream.append(MessagingEvent(event_type='mcp.group_permission.changed', subject='readers'))
        await stream.append(MessagingEvent(event_type='connector.capability_description_override.changed', subject='shared'))
        final_event = await stream.append(MessagingEvent(event_type='connector.capability_activation.changed', subject='shared'))
        async with asyncio.timeout(5):
            while health.last_applied_sequence < final_event.sequence:
                await asyncio.sleep(0.01)
        snapshot = context.mcp.downstream_mcp_discovery_runtime.capture()
        assert snapshot.available_records == ()
        assert snapshot.descriptions['shared'] == 'Updated shared connector'
        assert permissions.allowed_connector_ids(membership) == {'shared'}
        assert health.ready
