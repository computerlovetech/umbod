from typing import Annotated

from fastapi import Depends

from umbod.core.admin_overview.service import AdminOverviewService
from umbod.core.connectors.native.registry import ConnectorRegistry
from umbod.rest.connectors.native.dependencies import get_connector_registry
from umbod.rest.dependencies import get_connector_api_dependency_factories
from umbod.rest.factories import ConnectorApiDependencyFactories

from .reader import DatabaseOverviewReader


async def get_admin_overview_service(
    factories: Annotated[
        ConnectorApiDependencyFactories, Depends(get_connector_api_dependency_factories),
    ],
    registry: Annotated[ConnectorRegistry, Depends(get_connector_registry)],
) -> AdminOverviewService:
    await factories.persistence_runtime.readiness.ensure_ready()
    return AdminOverviewService(
        DatabaseOverviewReader(factories.persistence_runtime.database, registry),
    )
