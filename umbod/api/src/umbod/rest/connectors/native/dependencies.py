from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Query
from messaging.ports import EventStream
from pydantic import Field

from umbod.core.activation import (
    ActivationFilter,
    ActivationPort,
    ActivationStore,
    CapabilityActivationService,
    CapabilitySourceActivationCatalog,
    InMemoryActivationNotifier,
)
from umbod.core.capabilities.descriptions import ConnectorCapabilityDescriptionOverrideStore
from umbod.core.configuration import ConnectorCurrentConfigurationStore
from umbod.core.connectors.native.capabilities import NativeCapabilityCatalog
from umbod.core.connectors.native.registry import ConnectorRegistry
from umbod.core.publishing import ConnectorPublishingStore
from umbod.rest.connectors.dependencies import (
    get_capability_activation_store,
    get_connector_capability_description_override_store,
    get_connector_event_stream,
    get_connector_publishing_store,
)
from umbod.rest.connectors.native.service import (
    ConnectorPresentationService,
    StoreBackedConnectorPresentationService,
)
from umbod.rest.dependencies import get_connector_api_dependency_factories
from umbod.rest.factories import ConnectorApiDependencyFactories
from umbod.rest.proxies import Model


@dataclass(frozen=True)
class ConnectorPublicationDependencies:
    connector_registry: ConnectorRegistry
    configuration_store: ConnectorCurrentConfigurationStore
    publishing_store: ConnectorPublishingStore
    event_stream: EventStream | None


@dataclass(frozen=True)
class ConnectorConfigurationSaveDependencies:
    connector_registry: ConnectorRegistry
    store: ConnectorCurrentConfigurationStore
    event_stream: EventStream | None


class ActivationFilterQuery(Model):
    activation_status: ActivationFilter = Field(default=ActivationFilter.ALL)


def get_connector_registry(
    dependency_factories: Annotated[
        ConnectorApiDependencyFactories, Depends(get_connector_api_dependency_factories)
    ],
) -> ConnectorRegistry:
    return dependency_factories.connector_registry.create()


async def get_connector_current_configuration_store(
    dependency_factories: Annotated[
        ConnectorApiDependencyFactories, Depends(get_connector_api_dependency_factories)
    ],
) -> ConnectorCurrentConfigurationStore:
    await dependency_factories.persistence_runtime.readiness.ensure_ready()
    return await dependency_factories.connector_current_configuration_store.create()


def get_capability_activation_filter(
    query: Annotated[ActivationFilterQuery, Query()],
) -> ActivationFilter:
    return query.activation_status


def get_capability_activation_port(
    connector_registry: Annotated[ConnectorRegistry, Depends(get_connector_registry)],
    activation_store: Annotated[ActivationStore, Depends(get_capability_activation_store)],
) -> ActivationPort:
    capabilities = NativeCapabilityCatalog.from_registry(connector_registry)
    catalog = CapabilitySourceActivationCatalog(capabilities, activation_store, "native")
    return CapabilityActivationService(
        catalog=catalog, store=activation_store, notifier=InMemoryActivationNotifier()
    )


def get_connector_publication_dependencies(
    connector_registry: Annotated[ConnectorRegistry, Depends(get_connector_registry)],
    configuration_store: Annotated[
        ConnectorCurrentConfigurationStore, Depends(get_connector_current_configuration_store)
    ],
    publishing_store: Annotated[ConnectorPublishingStore, Depends(get_connector_publishing_store)],
    event_stream: Annotated[EventStream | None, Depends(get_connector_event_stream)],
) -> ConnectorPublicationDependencies:
    return ConnectorPublicationDependencies(
        connector_registry=connector_registry,
        configuration_store=configuration_store,
        publishing_store=publishing_store,
        event_stream=event_stream,
    )


def get_connector_presentation_service(
    configuration_store: Annotated[
        ConnectorCurrentConfigurationStore, Depends(get_connector_current_configuration_store)
    ],
    publishing_store: Annotated[ConnectorPublishingStore, Depends(get_connector_publishing_store)],
    override_store: Annotated[
        ConnectorCapabilityDescriptionOverrideStore,
        Depends(get_connector_capability_description_override_store),
    ],
) -> ConnectorPresentationService:
    return StoreBackedConnectorPresentationService(
        configuration_store, publishing_store, override_store
    )


def get_connector_configuration_save_dependencies(
    connector_registry: Annotated[ConnectorRegistry, Depends(get_connector_registry)],
    store: Annotated[
        ConnectorCurrentConfigurationStore, Depends(get_connector_current_configuration_store)
    ],
    event_stream: Annotated[EventStream | None, Depends(get_connector_event_stream)],
) -> ConnectorConfigurationSaveDependencies:
    return ConnectorConfigurationSaveDependencies(
        connector_registry=connector_registry, store=store, event_stream=event_stream
    )
