from typing import Annotated

from fastapi import Depends

from umbod.core.agent_behaviour import AgentBehaviourService, create_agent_behaviour_service
from umbod.rest.dependencies import get_connector_api_dependency_factories
from umbod.rest.factories import ConnectorApiDependencyFactories


def get_agent_behaviour_service(
    factories: Annotated[ConnectorApiDependencyFactories, Depends(get_connector_api_dependency_factories)],
) -> AgentBehaviourService:
    return create_agent_behaviour_service(factories.persistence_runtime.database)
