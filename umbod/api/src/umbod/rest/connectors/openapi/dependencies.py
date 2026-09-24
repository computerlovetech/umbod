from umbod.config.defaults import LOCAL_CONNECTOR_CONFIGURATION_SECRET
from umbod.core.configuration.persistence.factories import create_encrypted_connector_configuration_store

from datetime import UTC, datetime
from typing import Annotated
from uuid import uuid4
from fastapi import Depends, HTTPException, Request, status
from umbod.core.configuration import ConnectorConfigurationRegistry, ConnectorConfigurationService, EnvironmentConnectorConfigurationSecret
from umbod.core.activation import (
    ActivationPort,
    ActivationStore,
    CapabilityActivationService,
    CapabilitySourceActivationCatalog,
    InMemoryActivationNotifier,
)
from umbod.core.connectors.openapi.catalog import OpenApiConnectorToolCatalog, StoreBackedOpenApiCapabilityCatalog
from umbod.core.connectors.openapi.management import OpenApiBearerConfiguration, OpenApiConfigurationAdapter, OpenApiConfigurationPort, compose_openapi_connector_management, OpenApiConnectorManagementService, PersistedGroupPermissionActivationChangeGuard
from umbod.core.connectors.openapi.importing import InMemoryOpenApiCandidateImporter
from umbod.core.connectors.openapi.stores import OpenApiConnectorStore
from umbod.core.permissions.ports import GroupPermissionReader
from umbod.rest.connectors.dependencies import get_capability_activation_store
from umbod.rest.dependencies import get_connector_api_dependency_factories
from umbod.rest.factories import ConnectorApiDependencyFactories
from umbod.rest.mcp_permissions.dependencies import get_group_permission_store

class UuidOpenApiIdGenerator:

    def new_id(self) -> str:
        return str(uuid4())

class UtcOpenApiClock:

    def now(self) -> str:
        return datetime.now(UTC).isoformat()

async def get_openapi_connector_store(factories: Annotated[ConnectorApiDependencyFactories, Depends(get_connector_api_dependency_factories)]) -> OpenApiConnectorStore:
    await factories.persistence_runtime.readiness.ensure_ready()
    return await factories.openapi_connector_store.create()

def get_openapi_connector_management_service(store: Annotated[OpenApiConnectorStore, Depends(get_openapi_connector_store)], permissions: Annotated[GroupPermissionReader, Depends(get_group_permission_store)]) -> OpenApiConnectorManagementService:
    return compose_openapi_connector_management(store=store, ids=UuidOpenApiIdGenerator(), clock=UtcOpenApiClock(), permission_change_guard=PersistedGroupPermissionActivationChangeGuard(permissions))

def get_openapi_candidate_importer() -> InMemoryOpenApiCandidateImporter:
    return InMemoryOpenApiCandidateImporter()

async def get_openapi_configuration_port(factories: Annotated[ConnectorApiDependencyFactories, Depends(get_connector_api_dependency_factories)]) -> OpenApiConfigurationPort:
    await factories.persistence_runtime.readiness.ensure_ready()
    settings = factories.settings
    service = ConnectorConfigurationService(registry=ConnectorConfigurationRegistry({'openapi': OpenApiBearerConfiguration}), store=await create_encrypted_connector_configuration_store(factories.persistence_runtime.database), secret=EnvironmentConnectorConfigurationSecret.from_value(settings.connector_security.configuration_secret or LOCAL_CONNECTOR_CONFIGURATION_SECRET))
    return OpenApiConfigurationAdapter(service)

def get_openapi_tool_catalog(store: Annotated[OpenApiConnectorStore, Depends(get_openapi_connector_store)], activation_store: Annotated[ActivationStore, Depends(get_capability_activation_store)]) -> OpenApiConnectorToolCatalog:
    return OpenApiConnectorToolCatalog(store, activation_store)

def get_openapi_tool_activation_port(store: Annotated[OpenApiConnectorStore, Depends(get_openapi_connector_store)], activation_store: Annotated[ActivationStore, Depends(get_capability_activation_store)]) -> ActivationPort:
    catalog = CapabilitySourceActivationCatalog(StoreBackedOpenApiCapabilityCatalog(store), activation_store, 'openapi')
    return CapabilityActivationService(catalog=catalog, store=activation_store, notifier=InMemoryActivationNotifier())

def get_openapi_json_import_max_bytes(factories: Annotated[ConnectorApiDependencyFactories, Depends(get_connector_api_dependency_factories)]) -> int:
    return factories.openapi_json_import_max_bytes

async def enforce_openapi_json_import_max_bytes(request: Request, factories: Annotated[ConnectorApiDependencyFactories, Depends(get_connector_api_dependency_factories)]) -> None:
    max_bytes = factories.openapi_json_import_max_bytes
    content_length = request.headers.get('content-length')
    if content_length is not None and content_length.isdigit() and (int(content_length) > max_bytes):
        raise HTTPException(status_code=status.HTTP_413_CONTENT_TOO_LARGE, detail={'code': 'openapi_import_too_large', 'max_bytes': max_bytes})
    if len(await request.body()) > max_bytes:
        raise HTTPException(status_code=status.HTTP_413_CONTENT_TOO_LARGE, detail={'code': 'openapi_import_too_large', 'max_bytes': max_bytes})
