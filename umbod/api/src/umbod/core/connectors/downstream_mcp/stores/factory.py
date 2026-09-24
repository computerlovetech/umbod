from dataclasses import dataclass

from umbod.core.activation import ActivationStore, CAPABILITY_ACTIVATION_STATE_TABLE
from umbod.core.activation.stores.service import CapabilityActivationStoreService
from umbod.core.configuration.persistence import AuthenticatedTextCipher
from umbod.core.publishing import ConnectorPublishingStore
from umbod.core.publishing.stores.schema import PUBLICATION_STATE_TABLE
from umbod.core.publishing.stores.service import ConnectorPublishingStoreService
from umbod.core.connectors.downstream_mcp.management import (
    DownstreamConnectorUnitOfWork,
    DownstreamConnectorUnitOfWorkService,
    no_downstream_connector_mutation_fault,
    utc_clock,
)
from umbod.core.connectors.downstream_mcp.stores.catalogs import ToolCatalogStoreService
from umbod.core.connectors.downstream_mcp.stores.credentials import (
    EncryptedCredentialStoreService,
)
from umbod.core.connectors.downstream_mcp.stores.definitions import (
    ConnectorDefinitionStoreService,
)
from umbod.core.connectors.downstream_mcp.stores.health import ConnectorHealthStoreService
from umbod.core.connectors.downstream_mcp.stores.ports import (
    ConnectorDefinitionStore,
    ConnectorHealthStore,
    EncryptedCredentialStore,
    ToolCatalogStore,
)
from umbod.core.connectors.downstream_mcp.stores.schema import (
    CONNECTOR_CREDENTIAL_TABLE,
    CONNECTOR_DEFINITION_TABLE,
    CONNECTOR_HEALTH_TABLE,
    TOOL_CATALOG_TABLE,
)
from umbod.core.persistence import Database


@dataclass(frozen=True)
class DownstreamMcpStores:
    definitions: ConnectorDefinitionStore
    credentials: EncryptedCredentialStore
    catalogs: ToolCatalogStore
    health: ConnectorHealthStore
    publishing: ConnectorPublishingStore
    activations: ActivationStore
    unit_of_work: DownstreamConnectorUnitOfWork


async def create_downstream_mcp_stores(
    credential_secret: str,
    database: Database,
) -> DownstreamMcpStores:
    return DownstreamMcpStores(
        definitions=ConnectorDefinitionStoreService(database, CONNECTOR_DEFINITION_TABLE),
        credentials=EncryptedCredentialStoreService(
            database,
            CONNECTOR_CREDENTIAL_TABLE,
            AuthenticatedTextCipher(credential_secret),
        ),
        catalogs=ToolCatalogStoreService(database, TOOL_CATALOG_TABLE),
        health=ConnectorHealthStoreService(database, CONNECTOR_HEALTH_TABLE),
        publishing=ConnectorPublishingStoreService(database, PUBLICATION_STATE_TABLE),
        activations=CapabilityActivationStoreService(database, CAPABILITY_ACTIVATION_STATE_TABLE),
        unit_of_work=DownstreamConnectorUnitOfWorkService(
            database,
            AuthenticatedTextCipher(credential_secret),
            no_downstream_connector_mutation_fault,
            utc_clock,
        ),
    )
