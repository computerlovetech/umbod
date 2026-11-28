from typing import Annotated

from fastapi import Depends

from umbod.core.connectors.portable.managed.catalog import PortableConnectorCatalog
from umbod.core.connectors.portable.managed.catalog_store import (
    DatabaseManagedConnectorCatalogStore,
)
from umbod.core.connectors.portable.managed.ports import ManagedCatalogUnavailable
from umbod.rest.dependencies import get_connector_api_dependency_factories
from umbod.rest.factories import ConnectorApiDependencyFactories
from umbod.rest.system_settings.dependencies import (
    AdministratorRole,
    require_settings_administrator,
)


async def get_portable_connector_catalog(
    _administrator: Annotated[
        AdministratorRole, Depends(require_settings_administrator)
    ],
    factories: Annotated[
        ConnectorApiDependencyFactories, Depends(get_connector_api_dependency_factories)
    ],
) -> PortableConnectorCatalog:
    runtime = factories.persistence_runtime
    try:
        await runtime.readiness.ensure_ready()
    except Exception:
        raise ManagedCatalogUnavailable() from None
    return PortableConnectorCatalog(
        DatabaseManagedConnectorCatalogStore(runtime.database)
    )


PortableCatalogAccess = Annotated[
    PortableConnectorCatalog, Depends(get_portable_connector_catalog)
]
