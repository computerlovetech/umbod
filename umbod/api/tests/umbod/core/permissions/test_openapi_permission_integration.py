from umbod.core.activation import CAPABILITY_ACTIVATION_STATE_TABLE
from umbod.core.connectors.openapi.stores import CATALOG_OPERATION_TABLE, CATALOG_SOURCE_TABLE, CONNECTOR_TABLE, CURRENT_CATALOG_HEADER_TABLE, OpenApiConnectorStoreService
from tests.persistence_runtime import create_inmemory_runtime
import pytest
from umbod.core.capabilities import (
    UnrestrictedCapabilityActivation,
    UnrestrictedCapabilityPublication,
    UnrestrictedCapabilityReadiness,
)
from umbod.core.connectors.openapi.catalog import StoreBackedOpenApiCapabilityCatalog
from umbod.core.connectors.openapi.importing import InMemoryOpenApiCandidateImporter
from umbod.core.connectors.openapi.management import OpenApiConnector, OpenApiConnectorCatalog
from umbod.core.connectors.openapi.models import ImportedOpenApiCandidate
from umbod.core.connectors.openapi.stores import OpenApiConnectorStore
from umbod.core.permissions import AssignableConnectorPermissionTarget, AssignablePermissionCatalog, AssignablePermissionTargets, AssignableCapabilityPermissionTarget, CompositeConnectorToolPermissionCatalog, CapabilityPermissionCatalog, ConnectorToolRef

class FixedCatalog:

    def __init__(self, targets: AssignablePermissionTargets) -> None:
        self._targets = targets

    async def has_connector(self, connector_id: str) -> bool:
        return any((target.connector_id == connector_id for target in self._targets.connectors))

    async def has_capability(self, capability: object) -> bool:
        from umbod.core.permissions import ConnectorCapabilityRef

        if not isinstance(capability, ConnectorCapabilityRef):
            return False
        return any(
            (
                target.connector_id == capability.connector_id
                and target.capability_kind == capability.capability_kind
                and target.capability_key == capability.capability_key
            )
            for target in self._targets.capabilities
        )

    async def has_tool(self, tool: ConnectorToolRef) -> bool:
        return await self.has_capability(tool.as_capability())

    async def list_assignable_targets(self) -> AssignablePermissionTargets:
        return self._targets

def _candidate(operations: tuple[tuple[str, str], ...]) -> ImportedOpenApiCandidate:
    paths = {f'/items/{index}': {'get': {'operationId': operation_id, 'summary': summary, 'responses': {'200': {'description': 'OK'}}}} for (index, (operation_id, summary)) in enumerate(operations)}
    return InMemoryOpenApiCandidateImporter().import_candidate({'openapi': '3.1.0', 'info': {'title': 'API', 'version': '1'}, 'servers': [{'url': 'https://api.example.test'}], 'paths': paths})

def _connector(connector_id: str, display_name: str) -> OpenApiConnector:
    return OpenApiConnector.model_validate({'connector_id': connector_id, 'display_name': display_name, 'tool_name_prefix': display_name, 'capability_description': f'{display_name} capabilities', 'created_at': 'time', 'updated_at': 'time'})

def _catalog(connector_id: str, operations: tuple[tuple[str, str], ...]) -> OpenApiConnectorCatalog:
    candidate = _candidate(operations)
    return OpenApiConnectorCatalog(connector_id=connector_id, catalog_id=f'{connector_id}-catalog', source_document={}, candidate=candidate, approved_hosts=('api.example.test',), selected_server_url='https://api.example.test', operation_ids=tuple(sorted((endpoint.operation_id for endpoint in candidate.endpoints))), imported_at='time')

def _permission_catalog(store: OpenApiConnectorStore) -> AssignablePermissionCatalog:
    return CapabilityPermissionCatalog(StoreBackedOpenApiCapabilityCatalog(store), 'openapi', UnrestrictedCapabilityPublication(), UnrestrictedCapabilityActivation(), UnrestrictedCapabilityReadiness(), validate_connector_availability=False, validate_tool_availability=False, include_connector_without_tools=False)

async def _save(store: OpenApiConnectorStore, connector_id: str, display_name: str, operations: tuple[tuple[str, str], ...]) -> None:
    await store.save_connector(_connector(connector_id, display_name))
    await store.save_catalog(_catalog(connector_id, operations))

@pytest.mark.asyncio
async def test_catalog_scopes_overlapping_operation_ids_by_connector() -> None:
    store: OpenApiConnectorStore = OpenApiConnectorStoreService(create_inmemory_runtime().database, CONNECTOR_TABLE, CURRENT_CATALOG_HEADER_TABLE, CATALOG_SOURCE_TABLE, CATALOG_OPERATION_TABLE, CAPABILITY_ACTIVATION_STATE_TABLE)
    await _save(store, 'alpha', 'Alpha', (('listItems', 'List alpha'),))
    await _save(store, 'beta', 'Beta', (('listItems', 'List beta'),))
    catalog = _permission_catalog(store)
    assert await catalog.has_tool(ConnectorToolRef('alpha', 'listItems'))
    assert await catalog.has_tool(ConnectorToolRef('beta', 'listItems'))
    assert len((await catalog.list_assignable_targets()).tools) == 2

@pytest.mark.asyncio
async def test_catalog_excludes_connectors_without_a_current_catalog() -> None:
    store: OpenApiConnectorStore = OpenApiConnectorStoreService(create_inmemory_runtime().database, CONNECTOR_TABLE, CURRENT_CATALOG_HEADER_TABLE, CATALOG_SOURCE_TABLE, CATALOG_OPERATION_TABLE, CAPABILITY_ACTIVATION_STATE_TABLE)
    await _save(store, 'active', 'Active', (('current', 'Current'),))
    await store.save_connector(_connector('uncatalogued', 'Uncatalogued'))
    catalog = _permission_catalog(store)
    assert await catalog.list_assignable_targets() == AssignablePermissionTargets(connectors=(AssignableConnectorPermissionTarget('active', 'Active'),), capabilities=(AssignableCapabilityPermissionTarget('active', 'tool', 'current', 'Current'),))

@pytest.mark.asyncio
async def test_catalog_returns_deterministic_labels_and_order_with_operation_id_fallback() -> None:
    store: OpenApiConnectorStore = OpenApiConnectorStoreService(create_inmemory_runtime().database, CONNECTOR_TABLE, CURRENT_CATALOG_HEADER_TABLE, CATALOG_SOURCE_TABLE, CATALOG_OPERATION_TABLE, CAPABILITY_ACTIVATION_STATE_TABLE)
    await _save(store, 'zeta', 'Zeta', (('beta', ''), ('alpha', ' Alpha summary ')))
    await _save(store, 'alpha', 'Alpha', (('same', 'Same summary'),))
    catalog = _permission_catalog(store)
    assert await catalog.list_assignable_targets() == AssignablePermissionTargets(connectors=(AssignableConnectorPermissionTarget('alpha', 'Alpha'), AssignableConnectorPermissionTarget('zeta', 'Zeta')), capabilities=(AssignableCapabilityPermissionTarget('alpha', 'tool', 'same', 'Same summary'), AssignableCapabilityPermissionTarget('zeta', 'tool', 'alpha', 'Alpha summary'), AssignableCapabilityPermissionTarget('zeta', 'tool', 'beta', 'beta')))

@pytest.mark.asyncio
async def test_composite_catalog_merges_non_conflicting_catalogs_in_deterministic_order() -> None:
    first: AssignablePermissionCatalog = FixedCatalog(AssignablePermissionTargets(connectors=(AssignableConnectorPermissionTarget('zeta', 'Zeta'),), capabilities=(AssignableCapabilityPermissionTarget('zeta', 'tool', 'read', 'Read'),)))
    second: AssignablePermissionCatalog = FixedCatalog(AssignablePermissionTargets(connectors=(AssignableConnectorPermissionTarget('alpha', 'Alpha'),), capabilities=(AssignableCapabilityPermissionTarget('alpha', 'tool', 'write', 'Write'),)))
    targets = await CompositeConnectorToolPermissionCatalog((first, second)).list_assignable_targets()
    assert tuple((target.connector_id for target in targets.connectors)) == ('alpha', 'zeta')
    assert tuple(((target.connector_id, target.capability_key) for target in targets.tools)) == (('alpha', 'write'), ('zeta', 'read'))

@pytest.mark.parametrize('identity', ['connector', 'tool'])
@pytest.mark.asyncio
async def test_composite_catalog_rejects_conflicting_duplicate_identities(identity: str) -> None:
    connector_name = 'Different' if identity == 'connector' else 'Shared'
    tool_name = 'Different' if identity == 'tool' else 'Shared tool'
    first: AssignablePermissionCatalog = FixedCatalog(AssignablePermissionTargets(connectors=(AssignableConnectorPermissionTarget('shared', 'Shared'),), capabilities=(AssignableCapabilityPermissionTarget('shared', 'tool', 'read', 'Shared tool'),)))
    second: AssignablePermissionCatalog = FixedCatalog(AssignablePermissionTargets(connectors=(AssignableConnectorPermissionTarget('shared', connector_name),), capabilities=(AssignableCapabilityPermissionTarget('shared', 'tool', 'read', tool_name),)))
    with pytest.raises(ValueError, match=f'Duplicate {identity if identity == "connector" else "capability"}'):
        await CompositeConnectorToolPermissionCatalog((first, second)).list_assignable_targets()
