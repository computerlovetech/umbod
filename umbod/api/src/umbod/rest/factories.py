from umbod.config.defaults import LOCAL_CONNECTOR_CONFIGURATION_SECRET
from umbod.core.capabilities.descriptions.factories import (
    ConfiguredConnectorCapabilityDescriptionOverrideStoreFactory as InfrastructureConnectorCapabilityDescriptionOverrideStoreFactory,
)
from umbod.core.configuration.persistence.factories import (
    create_encrypted_connector_configuration_store,
)
from umbod.core.publishing.factories import (
    ConfiguredConnectorPublishingStoreFactory as InfrastructureConnectorPublishingStoreFactory,
)
from umbod.core.activation import create_capability_activation_store
from umbod.core.connectors.openapi.stores.factories import (
    ConfiguredOpenApiConnectorStoreFactory as InfrastructureOpenApiConnectorStoreFactory,
)
from umbod.core.permissions.factories import create_group_permission_store

from collections.abc import Callable, Sequence
from contextlib import AbstractAsyncContextManager
from functools import cached_property
from typing import Protocol
from umbod_sdk.connectors.discovery import load_connector_plugins
from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from umbod.core.messaging import DatabaseEventStream
from messaging.in_memory import InMemoryEventStreamFactory
from messaging.ports import EventStream
from umbod.core.capabilities.descriptions import ConnectorCapabilityDescriptionOverrideStore
from umbod.core.configuration import ConnectorConfigurationService, ConnectorCurrentConfigurationStore, EnvironmentConnectorConfigurationSecret
from umbod.core.connectors.native.configuration_adapter import ConnectorConfigurationSchemaRegistryAdapter
from umbod.core.connectors.native.deployment import CONNECTOR_DEPLOYMENT_CONFIGURATION_PATH_VARIABLE, deployment_connector_availability_source_from_environment
from umbod.core.publishing import ConnectorPublishingStore
from umbod.core.connectors.native.registry import ConnectorRegistration, ConnectorRegistry, InMemoryConnectorRegistry
from umbod.core.connectors.native.runtime import connector_registrations_from_plugins
from umbod.core.activation import ActivationStore
from umbod.core.connectors.downstream_mcp.stores import ConnectorDefinitionStore, ConnectorHealthStore, EncryptedCredentialStore, ToolCatalogStore
from umbod.core.configuration.persistence import AuthenticatedTextCipher
from umbod.core.connectors.downstream_mcp.stores.catalogs import ToolCatalogStoreService
from umbod.core.connectors.downstream_mcp.stores.credentials import EncryptedCredentialStoreService
from umbod.core.connectors.downstream_mcp.stores.definitions import ConnectorDefinitionStoreService
from umbod.core.connectors.downstream_mcp.stores.health import ConnectorHealthStoreService
from umbod.core.connectors.downstream_mcp.stores.schema import CONNECTOR_CREDENTIAL_TABLE, CONNECTOR_DEFINITION_TABLE, CONNECTOR_HEALTH_TABLE, TOOL_CATALOG_TABLE
from umbod.core.persistence import Database, PersistenceRuntime
from umbod.core.connectors.openapi.stores import OpenApiConnectorStore
from umbod.core.permissions import GroupPermissionStore
from umbod.core.connectors.downstream_mcp.adapters.settings import (
    downstream_mcp_infrastructure_settings_from_app_config,
)
from umbod.rest.settings import APISettings

class ConnectorRegistryFactory(Protocol):

    def create(self) -> ConnectorRegistry:
        ...

class ConnectorRegistrationSource(Protocol):

    def load(self) -> Sequence[ConnectorRegistration]:
        ...

class ConnectorCurrentConfigurationStoreFactory(Protocol):

    async def create(self) -> ConnectorCurrentConfigurationStore:
        ...

class ConnectorPublishingStoreFactory(Protocol):

    async def create(self) -> ConnectorPublishingStore:
        ...

class CapabilityActivationStoreFactory(Protocol):

    async def create(self) -> ActivationStore:
        ...

class EventStreamFactory(Protocol):

    def create(self) -> EventStream | None:
        ...

class GroupPermissionStoreFactory(Protocol):

    async def create(self) -> GroupPermissionStore:
        ...

class OpenApiConnectorStoreFactory(Protocol):

    async def create(self) -> OpenApiConnectorStore:
        ...

class DownstreamMcpDefinitionStoreFactory(Protocol):

    def create(self) -> ConnectorDefinitionStore:
        ...

class DownstreamMcpCredentialStoreFactory(Protocol):

    def create(self) -> EncryptedCredentialStore:
        ...

class DownstreamMcpCatalogStoreFactory(Protocol):

    def create(self) -> ToolCatalogStore:
        ...

class DownstreamMcpHealthStoreFactory(Protocol):

    def create(self) -> ConnectorHealthStore:
        ...

class RootApiAppFactory:

    def __init__(self, settings: APISettings) -> None:
        self.settings = settings

    def create(self) -> FastAPI:
        app = FastAPI(title='umbod-api', docs_url=None, openapi_url=None, redoc_url=None)
        self._add_middleware(app)
        return app

    def _add_middleware(self, app: FastAPI) -> None:
        app.add_middleware(CORSMiddleware, allow_origins=self.settings.cors.origins, allow_credentials=False, allow_methods=['*'], allow_headers=['*'])

class LifespanRootApiAppFactory(RootApiAppFactory):

    def __init__(self, settings: APISettings, lifespan: Callable[[FastAPI], AbstractAsyncContextManager[None]]) -> None:
        super().__init__(settings)
        self.lifespan = lifespan

    def create(self) -> FastAPI:
        app = FastAPI(title='umbod-api', docs_url=None, openapi_url=None, redoc_url=None, lifespan=self.lifespan)
        self._add_middleware(app)
        return app

class SubApiAppFactory:

    def __init__(self, title: str, router: APIRouter) -> None:
        self.title = title
        self.router = router

    def create(self) -> FastAPI:
        sub_app = FastAPI(title=self.title, version='0.0.1', docs_url='/docs', openapi_url='/openapi.json')
        sub_app.include_router(self.router)
        return sub_app

class ConnectorApiDependencyFactories:

    def __init__(self, *, connector_registry: ConnectorRegistryFactory, connector_current_configuration_store: ConnectorCurrentConfigurationStoreFactory, connector_publishing_store: ConnectorPublishingStoreFactory, capability_activation_store: CapabilityActivationStoreFactory, event_stream: EventStreamFactory, group_permission_store: GroupPermissionStoreFactory, openapi_connector_store: OpenApiConnectorStoreFactory, downstream_mcp_definition_store: DownstreamMcpDefinitionStoreFactory, downstream_mcp_credential_store: DownstreamMcpCredentialStoreFactory, downstream_mcp_catalog_store: DownstreamMcpCatalogStoreFactory, downstream_mcp_health_store: DownstreamMcpHealthStoreFactory, openapi_json_import_max_bytes: int, settings: APISettings, persistence_runtime: PersistenceRuntime) -> None:
        self.settings = settings
        self.connector_registry = connector_registry
        self.connector_current_configuration_store = connector_current_configuration_store
        self.connector_publishing_store = connector_publishing_store
        self.capability_activation_store = capability_activation_store
        self.persistence_runtime = persistence_runtime
        self.connector_capability_description_override_store = ConfiguredConnectorCapabilityDescriptionOverrideStoreFactory(persistence_runtime.database)
        self.event_stream = event_stream
        self.group_permission_store = group_permission_store
        self.openapi_connector_store = openapi_connector_store
        self.downstream_mcp_definition_store = downstream_mcp_definition_store
        self.downstream_mcp_credential_store = downstream_mcp_credential_store
        self.downstream_mcp_catalog_store = downstream_mcp_catalog_store
        self.downstream_mcp_health_store = downstream_mcp_health_store
        self.openapi_json_import_max_bytes = openapi_json_import_max_bytes

    def validate_startup(self) -> None:
        self.connector_registry.create()

    @classmethod
    def from_settings(cls, settings: APISettings, persistence_runtime: PersistenceRuntime, *connector_registrations: Sequence[ConnectorRegistration] | None) -> 'ConnectorApiDependencyFactories':
        connector_registry = ConfiguredConnectorRegistryFactory(*connector_registrations)
        return cls(connector_registry=connector_registry, connector_current_configuration_store=ConfiguredConnectorCurrentConfigurationStoreFactory(settings, connector_registry, persistence_runtime.database), connector_publishing_store=ConfiguredConnectorPublishingStoreFactory(persistence_runtime.database), capability_activation_store=ConfiguredCapabilityActivationStoreFactory(persistence_runtime.database), event_stream=ConfiguredEventStreamFactory(settings, persistence_runtime.database), group_permission_store=ConfiguredGroupPermissionStoreFactory(persistence_runtime.database), openapi_connector_store=ConfiguredOpenApiConnectorStoreFactory(persistence_runtime.database), downstream_mcp_definition_store=ConfiguredDownstreamMcpDefinitionStoreFactory(persistence_runtime.database), downstream_mcp_credential_store=ConfiguredDownstreamMcpCredentialStoreFactory(settings, persistence_runtime.database), downstream_mcp_catalog_store=ConfiguredDownstreamMcpCatalogStoreFactory(persistence_runtime.database), downstream_mcp_health_store=ConfiguredDownstreamMcpHealthStoreFactory(persistence_runtime.database), openapi_json_import_max_bytes=settings.openapi_connectors.json_import_max_bytes, settings=settings, persistence_runtime=persistence_runtime)

class StaticConnectorRegistrationSource:

    def __init__(self, connector_registrations: Sequence[ConnectorRegistration]) -> None:
        self.connector_registrations = connector_registrations

    def load(self) -> Sequence[ConnectorRegistration]:
        return self.connector_registrations

class PluginConnectorRegistrationSource:

    def load(self) -> Sequence[ConnectorRegistration]:
        return connector_registrations_from_plugins(load_connector_plugins(False))

class ConfiguredConnectorRegistryFactory:

    def __init__(self, *connector_registrations: Sequence[ConnectorRegistration] | None) -> None:
        self.registration_source = self._registration_source_from_arguments(connector_registrations)

    @classmethod
    def from_registrations(cls, connector_registrations: Sequence[ConnectorRegistration]) -> 'ConfiguredConnectorRegistryFactory':
        return cls(connector_registrations)

    @classmethod
    def from_plugins(cls) -> 'ConfiguredConnectorRegistryFactory':
        return cls()

    def create(self) -> ConnectorRegistry:
        return self._connector_registry

    @cached_property
    def _connector_registry(self) -> InMemoryConnectorRegistry:
        availability = deployment_connector_availability_source_from_environment(CONNECTOR_DEPLOYMENT_CONFIGURATION_PATH_VARIABLE).load()
        return InMemoryConnectorRegistry(self.registration_source.load(), available_connector_ids=availability.connector_ids)

    def _registration_source_from_arguments(self, connector_registrations: tuple[Sequence[ConnectorRegistration] | None, ...]) -> ConnectorRegistrationSource:
        if len(connector_registrations) > 1:
            raise TypeError('ConfiguredConnectorRegistryFactory() takes from 0 to 1 positional arguments')
        if connector_registrations and connector_registrations[0] is not None:
            return StaticConnectorRegistrationSource(connector_registrations[0])
        return PluginConnectorRegistrationSource()

class ConfiguredConnectorCurrentConfigurationStoreFactory:

    def __init__(self, settings: APISettings, connector_registry: ConnectorRegistryFactory, database: Database) -> None:
        self.settings = settings
        self.connector_registry = connector_registry
        self.database = database
        self._store: ConnectorConfigurationService | None = None

    async def create(self) -> ConnectorCurrentConfigurationStore:
        if self._store is None:
            self._store = ConnectorConfigurationService(registry=ConnectorConfigurationSchemaRegistryAdapter(self.connector_registry.create()), store=await create_encrypted_connector_configuration_store(self.database), secret=EnvironmentConnectorConfigurationSecret.from_value(self.settings.connector_security.configuration_secret or LOCAL_CONNECTOR_CONFIGURATION_SECRET))
        return self._store

class ConfiguredConnectorCapabilityDescriptionOverrideStoreFactory:

    def __init__(self, database: Database) -> None:
        self._factory = InfrastructureConnectorCapabilityDescriptionOverrideStoreFactory(database)

    async def create(self) -> ConnectorCapabilityDescriptionOverrideStore:
        return await self._factory.create()

class ConfiguredConnectorPublishingStoreFactory:

    def __init__(self, database: Database) -> None:
        self._factory = InfrastructureConnectorPublishingStoreFactory(database)
        self._store: ConnectorPublishingStore | None = None

    async def create(self) -> ConnectorPublishingStore:
        if self._store is None:
            self._store = await self._factory()
        return self._store

class ConfiguredCapabilityActivationStoreFactory:

    def __init__(self, database: Database) -> None:
        self.database = database
        self._store: ActivationStore | None = None

    async def create(self) -> ActivationStore:
        if self._store is None:
            self._store = await create_capability_activation_store(self.database)
        return self._store

class ConfiguredEventStreamFactory:

    def __init__(self, settings: APISettings, database: Database) -> None:
        self._settings = settings
        self._database = database

    def create(self) -> EventStream:
        return self._event_stream

    @cached_property
    def _event_stream(self) -> EventStream:
        if self._settings.mcp.messaging_transport == 'sql':
            return DatabaseEventStream(self._database)
        return InMemoryEventStreamFactory('Event stream is closed').create()

class ConfiguredOpenApiConnectorStoreFactory:

    def __init__(self, database: Database) -> None:
        self._factory = InfrastructureOpenApiConnectorStoreFactory(database)

    async def create(self) -> OpenApiConnectorStore:
        return await self._factory.create()

class ConfiguredDownstreamMcpDefinitionStoreFactory:

    def __init__(self, database: Database) -> None:
        self.database = database

    def create(self) -> ConnectorDefinitionStore:
        return ConnectorDefinitionStoreService(self.database, CONNECTOR_DEFINITION_TABLE)

class ConfiguredDownstreamMcpCredentialStoreFactory:

    def __init__(self, settings: APISettings, database: Database) -> None:
        self.settings = settings
        self.database = database

    def create(self) -> EncryptedCredentialStore:
        settings = downstream_mcp_infrastructure_settings_from_app_config(self.settings)
        return EncryptedCredentialStoreService(self.database, CONNECTOR_CREDENTIAL_TABLE, AuthenticatedTextCipher(settings.credential_secret))

class ConfiguredDownstreamMcpCatalogStoreFactory:

    def __init__(self, database: Database) -> None:
        self.database = database

    def create(self) -> ToolCatalogStore:
        return ToolCatalogStoreService(self.database, TOOL_CATALOG_TABLE)

class ConfiguredDownstreamMcpHealthStoreFactory:

    def __init__(self, database: Database) -> None:
        self.database = database

    def create(self) -> ConnectorHealthStore:
        return ConnectorHealthStoreService(self.database, CONNECTOR_HEALTH_TABLE)

class ConfiguredGroupPermissionStoreFactory:

    def __init__(self, database: Database) -> None:
        self.database = database
        self._store: GroupPermissionStore | None = None

    async def create(self) -> GroupPermissionStore:
        if self._store is None:
            self._store = await create_group_permission_store(self.database)
        return self._store
