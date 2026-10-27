from typing import Annotated

from fastapi import Depends

from umbod.config import AppConfig
from umbod.rest.authentication.local import LOCAL_DEVELOPMENT_ISSUER, local_rest_identity_enabled
from umbod.rest.instance_configuration.dependencies import get_app_config
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
    config: Annotated[AppConfig, Depends(get_app_config)],
) -> RootGroupPolicyManagement:
    issuer = LOCAL_DEVELOPMENT_ISSUER if local_rest_identity_enabled(config) else config.oidc.issuer_url
    return create_root_group_policy_management(database=database, issuer=issuer)
