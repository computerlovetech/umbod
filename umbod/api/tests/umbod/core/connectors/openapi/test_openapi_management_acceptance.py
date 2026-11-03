from umbod.core.activation import CAPABILITY_ACTIVATION_STATE_TABLE
from umbod.core.connectors.openapi.stores import CATALOG_OPERATION_TABLE, CATALOG_SOURCE_TABLE, CONNECTOR_TABLE, CURRENT_CATALOG_HEADER_TABLE, OpenApiConnectorStoreService
from tests.persistence_runtime import create_inmemory_runtime
from typing import Protocol
import pytest
from umbod.core.connectors.openapi.importing import InMemoryOpenApiCandidateImporter
from umbod.core.connectors.openapi.management import AllowActivationPermissionChangeGuard, compose_openapi_connector_management
from umbod.core.connectors.openapi.management import CreateOpenApiConnector, ImportOpenApiCatalog, OpenApiConnector, OpenApiConnectorCatalog
from umbod.core.connectors.openapi.models import ImportedOpenApiCandidate
pytestmark = pytest.mark.asyncio

class OpenApiConnectorManagement(Protocol):

    async def create_connector(self, request: CreateOpenApiConnector) -> OpenApiConnector:
        ...

    async def import_catalog(self, request: ImportOpenApiCatalog) -> OpenApiConnectorCatalog:
        ...

    async def get_connector(self, connector_id: str) -> OpenApiConnector:
        ...

class SequenceIds:

    def __init__(self) -> None:
        self._next_id = 0

    def new_id(self) -> str:
        self._next_id += 1
        return f'id-{self._next_id}'

class SequenceClock:

    def __init__(self) -> None:
        self._next_tick = 0

    def now(self) -> str:
        self._next_tick += 1
        return f'2026-01-01T00:00:0{self._next_tick}Z'

async def _service() -> OpenApiConnectorManagement:
    return compose_openapi_connector_management(store=OpenApiConnectorStoreService(create_inmemory_runtime().database, CONNECTOR_TABLE, CURRENT_CATALOG_HEADER_TABLE, CATALOG_SOURCE_TABLE, CATALOG_OPERATION_TABLE, CAPABILITY_ACTIVATION_STATE_TABLE), ids=SequenceIds(), clock=SequenceClock(), permission_change_guard=AllowActivationPermissionChangeGuard())

def _candidate(operation_id: str, server_url: str='https://api.example.test') -> ImportedOpenApiCandidate:
    return InMemoryOpenApiCandidateImporter().import_candidate({'openapi': '3.1.0', 'info': {'title': 'API', 'version': '1'}, 'servers': [{'url': server_url}], 'paths': {'/items': {'get': {'operationId': operation_id, 'responses': {'200': {'description': 'OK'}}}}}})

def _import_request(connector_id: str, operation_id: str, approved_hosts: tuple[str, ...]=('api.example.test',)) -> ImportOpenApiCatalog:
    return ImportOpenApiCatalog(connector_id=connector_id, source_document={'catalog': operation_id}, candidate=_candidate(operation_id), approved_hosts=approved_hosts)

async def test_create_connector_validates_and_persists_capability_description() -> None:
    service = await _service()
    connector = await service.create_connector(CreateOpenApiConnector(display_name='Inventory', tool_name_prefix='Inventory API!', capability_description='  Search and manage inventory  '))
    assert connector.capability_description == 'Search and manage inventory'
    assert connector.tool_name_prefix == 'Inventory_API'
    assert (await service.get_connector(connector.connector_id)).tool_name_prefix == 'Inventory_API'
    assert (await service.get_connector(connector.connector_id)).capability_description == 'Search and manage inventory'
    assert (await service.list_connectors())[0].capability_description == 'Search and manage inventory'

async def test_manages_multiple_connectors_with_overlapping_operation_ids() -> None:
    service = await _service()
    first = await service.create_connector(CreateOpenApiConnector(display_name='First', tool_name_prefix='First', capability_description='Manage first API resources'))
    second = await service.create_connector(CreateOpenApiConnector(display_name='Second', tool_name_prefix='Second', capability_description='Manage second API resources'))
    first_catalog = await service.import_catalog(_import_request(first.connector_id, 'listItems'))
    second_catalog = await service.import_catalog(_import_request(second.connector_id, 'listItems'))
    assert first.connector_id != second.connector_id
    assert first_catalog.connector_id == first.connector_id
    assert second_catalog.connector_id == second.connector_id
    assert first_catalog.operation_ids == second_catalog.operation_ids == ('listItems',)

async def test_reimport_immediately_replaces_current_catalog() -> None:
    service = await _service()
    connector = await service.create_connector(CreateOpenApiConnector(display_name='Inventory', tool_name_prefix='Inventory', capability_description='Manage inventory resources'))
    first = await service.import_catalog(_import_request(connector.connector_id, 'listItems'))
    second = await service.import_catalog(_import_request(connector.connector_id, 'searchItems'))
    assert first.catalog_id != second.catalog_id
    assert first.operation_ids == ('listItems',)
    assert second.operation_ids == ('searchItems',)

async def test_import_resolves_server_and_requires_approved_exact_host() -> None:
    service = await _service()
    connector = await service.create_connector(CreateOpenApiConnector(display_name='Inventory', tool_name_prefix='Inventory', capability_description='Manage inventory resources'))
    with pytest.raises(ValueError, match='eligible server'):
        await service.import_catalog(_import_request(connector.connector_id, 'listItems', approved_hosts=('other.test',)))

async def test_import_selects_the_single_eligible_server() -> None:
    service = await _service()
    connector = await service.create_connector(CreateOpenApiConnector(display_name='Inventory', tool_name_prefix='Inventory', capability_description='Manage inventory resources'))
    catalog = await service.import_catalog(_import_request(connector.connector_id, 'listItems'))
    assert catalog.selected_server_url == 'https://api.example.test'
