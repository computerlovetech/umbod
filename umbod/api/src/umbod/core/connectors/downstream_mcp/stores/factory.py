from dataclasses import dataclass

from ..personal_tools.ports import PersonalToolDiscoveryReader
from .personal_tool_discovery import PersonalToolDiscoveryStore

from ..personal_connections.refresh_ports import PersonalRefreshStore
from .personal_refresh import EncryptedPersonalRefreshStore

from ..personal_connections.health_ports import PersonalAuthorizationHealthStore
from .personal_authorization_health import EncryptedPersonalAuthorizationHealthStore

from ..personal_tools import PersonalToolAccessStore, PersonalToolPolicyStore
from .personal_tool_access import EncryptedPersonalToolAccessStore
from .personal_tool_policies import PersonalToolPolicyStoreService

from ..personal_connections.runtime_ports import PersonalRuntimeAuthorizationStore
from .personal_runtime_authorizations import EncryptedPersonalRuntimeAuthorizationStore

from umbod.core.connectors.downstream_mcp.personal_oauth_configuration import PersonalOAuthConfigurationStore
from umbod.core.connectors.downstream_mcp.stores.personal_oauth_configurations import EncryptedPersonalOAuthConfigurationStore

from umbod.core.connectors.downstream_mcp.personal_connections.oauth_ports import PersonalOAuthAttemptStore
from umbod.core.connectors.downstream_mcp.stores.personal_oauth_attempts import EncryptedPersonalOAuthAttemptStore

from umbod.core.connectors.downstream_mcp.personal_connections import PersonalConnectionStore
from umbod.core.connectors.downstream_mcp.stores.personal_connections import DefinitionBoundPersonalConnectionStore

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
    personal_tool_policies: PersonalToolPolicyStore
    personal_tool_access: PersonalToolAccessStore
    personal_tool_discovery: PersonalToolDiscoveryReader
    personal_runtime_authorizations: PersonalRuntimeAuthorizationStore
    personal_authorization_health: PersonalAuthorizationHealthStore
    personal_refresh: PersonalRefreshStore
    personal_connections: PersonalConnectionStore
    personal_oauth_attempts: PersonalOAuthAttemptStore
    personal_oauth_configurations: PersonalOAuthConfigurationStore


async def create_downstream_mcp_stores(
    credential_secret: str,
    database: Database,
) -> DownstreamMcpStores:
    return DownstreamMcpStores(
        personal_refresh=EncryptedPersonalRefreshStore(database, AuthenticatedTextCipher(credential_secret), utc_clock),
        personal_authorization_health=EncryptedPersonalAuthorizationHealthStore(database, AuthenticatedTextCipher(credential_secret)),
        personal_tool_policies=PersonalToolPolicyStoreService(database, utc_clock, no_downstream_connector_mutation_fault),
        personal_tool_access=EncryptedPersonalToolAccessStore(database, AuthenticatedTextCipher(credential_secret)),
        personal_tool_discovery=PersonalToolDiscoveryStore(database, AuthenticatedTextCipher(credential_secret)),
        personal_runtime_authorizations=EncryptedPersonalRuntimeAuthorizationStore(database, AuthenticatedTextCipher(credential_secret)),
        personal_oauth_configurations=EncryptedPersonalOAuthConfigurationStore(database, AuthenticatedTextCipher(credential_secret)),
        personal_oauth_attempts=EncryptedPersonalOAuthAttemptStore(
            database, AuthenticatedTextCipher(credential_secret), utc_clock
        ),
        personal_connections=DefinitionBoundPersonalConnectionStore(
            database, AuthenticatedTextCipher(credential_secret)
        ),
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
