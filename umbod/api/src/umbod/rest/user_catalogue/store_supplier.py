from umbod.core.connectors.downstream_mcp.adapters.settings import (
    downstream_mcp_infrastructure_settings_from_app_config,
)
from umbod.core.connectors.downstream_mcp.stores import (
    DownstreamMcpStores,
    create_downstream_mcp_stores,
)
from umbod.core.persistence import PersistenceRuntime
from umbod.rest.settings import APISettings


class ConfiguredPersonalCatalogueStoreSupplier:
    def __init__(self, settings: APISettings, persistence_runtime: PersistenceRuntime) -> None:
        self.settings = settings
        self.persistence_runtime = persistence_runtime

    async def create(self) -> DownstreamMcpStores:
        settings = downstream_mcp_infrastructure_settings_from_app_config(self.settings)
        await self.persistence_runtime.readiness.ensure_ready()
        return await create_downstream_mcp_stores(
            settings.credential_secret, self.persistence_runtime.database,
        )
