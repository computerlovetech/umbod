from typing import Annotated

from fastapi import Depends

from umbod.config import AppConfig
from umbod.config.identity_policy import filesystem_managed_issuer
from umbod.rest.instance_configuration.dependencies import get_app_config
from umbod.core.persistence import Database
from umbod.infrastructure import create_filesystem_namespace_management
from umbod.core.filesystem.namespaces import NamespaceManagement
from umbod.rest.dependencies import get_connector_api_dependency_factories
from umbod.rest.factories import ConnectorApiDependencyFactories


async def get_policy_database(
    factories: Annotated[ConnectorApiDependencyFactories, Depends(get_connector_api_dependency_factories)],
) -> Database:
    await factories.persistence_runtime.readiness.ensure_ready()
    return factories.persistence_runtime.database


def get_namespace_management(
    database: Annotated[Database, Depends(get_policy_database)],
    config: Annotated[AppConfig, Depends(get_app_config)],
) -> NamespaceManagement:
    return create_filesystem_namespace_management(database=database, issuer=filesystem_managed_issuer(config))
