from typing import Annotated

from fastapi import Depends
from messaging.ports import EventStream

from umbod.core.configuration import ConnectorCurrentConfigurationStore
from umbod.core.publishing import ConnectorPublishingStore
from umbod.core.connectors.native.registry import ConnectorRegistry
from umbod.core.activation import ActivationStore

from umbod.rest.dependencies import get_connector_api_dependency_factories
from umbod.rest.factories import ConnectorApiDependencyFactories


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


async def get_connector_publishing_store(
    dependency_factories: Annotated[
        ConnectorApiDependencyFactories, Depends(get_connector_api_dependency_factories)
    ],
) -> ConnectorPublishingStore:
    await dependency_factories.persistence_runtime.readiness.ensure_ready()
    return await dependency_factories.connector_publishing_store.create()


async def get_capability_activation_store(
    dependency_factories: Annotated[
        ConnectorApiDependencyFactories, Depends(get_connector_api_dependency_factories)
    ],
) -> ActivationStore:
    await dependency_factories.persistence_runtime.readiness.ensure_ready()
    return await dependency_factories.capability_activation_store.create()


def get_event_stream(
    dependency_factories: Annotated[
        ConnectorApiDependencyFactories, Depends(get_connector_api_dependency_factories)
    ],
) -> EventStream | None:
    return dependency_factories.event_stream.create()
