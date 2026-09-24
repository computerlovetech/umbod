from typing import Annotated

from fastapi import Depends
from messaging.ports import EventStream

from umbod.core.activation import ActivationStore
from umbod.core.capabilities.descriptions import ConnectorCapabilityDescriptionOverrideStore
from umbod.core.invocation import (
    ConnectorInvocationPolicyStore,
    DatabaseConnectorInvocationPolicyStore,
)
from umbod.core.invocation.tools.configuration_mutation import (
    ConnectorToolConfigurationMutationPort,
)
from umbod.core.invocation.tools.database_configuration_mutation import (
    DatabaseConnectorToolConfigurationMutationAdapter,
)
from umbod.core.publishing import ConnectorPublishingStore
from umbod.rest.dependencies import get_connector_api_dependency_factories
from umbod.rest.factories import ConnectorApiDependencyFactories


async def get_connector_publishing_store(
    dependency_factories: Annotated[
        ConnectorApiDependencyFactories, Depends(get_connector_api_dependency_factories)
    ],
) -> ConnectorPublishingStore:
    await dependency_factories.persistence_runtime.readiness.ensure_ready()
    return await dependency_factories.connector_publishing_store.create()


async def get_connector_invocation_policy_store(
    dependency_factories: Annotated[
        ConnectorApiDependencyFactories, Depends(get_connector_api_dependency_factories)
    ],
) -> ConnectorInvocationPolicyStore:
    await dependency_factories.persistence_runtime.readiness.ensure_ready()
    return DatabaseConnectorInvocationPolicyStore(
        dependency_factories.persistence_runtime.database
    )


async def get_connector_tool_configuration_mutation_port(
    dependency_factories: Annotated[
        ConnectorApiDependencyFactories, Depends(get_connector_api_dependency_factories)
    ],
) -> ConnectorToolConfigurationMutationPort:
    await dependency_factories.persistence_runtime.readiness.ensure_ready()
    return DatabaseConnectorToolConfigurationMutationAdapter(
        dependency_factories.persistence_runtime.database
    )


async def get_capability_activation_store(
    dependency_factories: Annotated[
        ConnectorApiDependencyFactories, Depends(get_connector_api_dependency_factories)
    ],
) -> ActivationStore:
    await dependency_factories.persistence_runtime.readiness.ensure_ready()
    return await dependency_factories.capability_activation_store.create()


async def get_connector_event_stream(
    dependency_factories: Annotated[
        ConnectorApiDependencyFactories, Depends(get_connector_api_dependency_factories)
    ],
) -> EventStream | None:
    await dependency_factories.persistence_runtime.readiness.ensure_ready()
    return dependency_factories.event_stream.create()


async def get_connector_capability_description_override_store(
    dependency_factories: Annotated[
        ConnectorApiDependencyFactories, Depends(get_connector_api_dependency_factories)
    ],
) -> ConnectorCapabilityDescriptionOverrideStore:
    await dependency_factories.persistence_runtime.readiness.ensure_ready()
    return await dependency_factories.connector_capability_description_override_store.create()
