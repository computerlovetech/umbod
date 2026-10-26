from typing import Annotated

from fastapi import Depends

from umbod.core.groups import GroupManagementService
from umbod.core.groups.stores.composition import create_group_management
from umbod.rest.dependencies import get_connector_api_dependency_factories
from umbod.rest.factories import ConnectorApiDependencyFactories


async def get_group_management(
    factories: Annotated[
        ConnectorApiDependencyFactories, Depends(get_connector_api_dependency_factories)
    ],
) -> GroupManagementService:
    await factories.persistence_runtime.readiness.ensure_ready()
    return create_group_management(factories.persistence_runtime.database)
