from typing import Annotated

from fastapi import Depends

from umbod.core.filesystem.administration import RootGroupPolicyManagement
from umbod.core.persistence import Database
from umbod.infrastructure import create_root_group_policy_management
from umbod.rest.dependencies import get_connector_api_dependency_factories
from umbod.rest.factories import ConnectorApiDependencyFactories


async def get_policy_database(
    factories: Annotated[ConnectorApiDependencyFactories, Depends(get_connector_api_dependency_factories)],
) -> Database:
    await factories.persistence_runtime.readiness.ensure_ready()
    return factories.persistence_runtime.database


def get_root_group_policy_management(
    database: Annotated[Database, Depends(get_policy_database)],
) -> RootGroupPolicyManagement:
    return create_root_group_policy_management(database=database)
