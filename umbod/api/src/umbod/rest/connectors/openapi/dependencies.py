from __future__ import annotations

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
from umbod.core.connectors.openapi.importing import DefaultOpenApiImportPreparer, InMemoryOpenApiCandidateImporter
from umbod.core.connectors.openapi.management.setup import OpenApiConnectorSetupService
from umbod.core.connectors.openapi.management.setup_ports import OpenApiConnectorSetupPort
from umbod.rest.connectors.openapi.schemas import SetupOpenApiConnectorRequest
from umbod.rest.connectors.openapi.file_import import decode_json_request_object
from pydantic import ValidationError
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

def get_openapi_connector_setup_port(
    management: Annotated[OpenApiConnectorManagementService, Depends(get_openapi_connector_management_service)],
    importer: Annotated[InMemoryOpenApiCandidateImporter, Depends(get_openapi_candidate_importer)],
    configuration: Annotated[OpenApiConfigurationPort, Depends(get_openapi_configuration_port)],
) -> OpenApiConnectorSetupPort:
    return OpenApiConnectorSetupService(management, importer, DefaultOpenApiImportPreparer(), configuration)


async def get_openapi_setup_request(
    request: Request,
    content: Annotated[bytes, Depends(enforce_openapi_json_import_max_bytes)],
) -> SetupOpenApiConnectorRequest:
    if request.headers.get('content-type', '').split(';', 1)[0].strip().lower() != 'application/json':
        raise HTTPException(status_code=415, detail={'code': 'openapi_import_unsupported_media_type'})
    try:
        return SetupOpenApiConnectorRequest.model_validate(decode_json_request_object(content))
    except ValidationError as error:
        raise HTTPException(status_code=422, detail={'code': 'openapi_setup_invalid_request'}) from error


async def enforce_openapi_json_import_max_bytes(request: Request, factories: Annotated[ConnectorApiDependencyFactories, Depends(get_connector_api_dependency_factories)]) -> bytes:
    max_bytes = factories.openapi_json_import_max_bytes
    content_length = request.headers.get('content-length')
    if content_length is not None and content_length.isdigit() and (int(content_length) > max_bytes):
        raise HTTPException(status_code=status.HTTP_413_CONTENT_TOO_LARGE, detail={'code': 'openapi_import_too_large', 'max_bytes': max_bytes})
    chunks: list[bytes] = []
    total_bytes = 0
    async for chunk in request.stream():
        total_bytes += len(chunk)
        if total_bytes > max_bytes:
            raise HTTPException(status_code=status.HTTP_413_CONTENT_TOO_LARGE, detail={'code': 'openapi_import_too_large', 'max_bytes': max_bytes})
        chunks.append(chunk)
    return b''.join(chunks)
