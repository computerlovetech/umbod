from collections.abc import Callable
from datetime import UTC, datetime
from typing import Protocol

from messaging.ports import EventStream
from umbod.core.activation import ActivationStore, create_capability_activation_store
from umbod.core.configuration.persistence import AuthenticatedTextCipher
from umbod.core.connectors.downstream_mcp.management import (
    CreateDownstreamConnectorAggregate,
    DownstreamConnectorUnitOfWork,
    DownstreamConnectorUnitOfWorkService,
    PreservePublication,
    ReconcileActivation,
    ReplaceCatalog,
    ReplaceCredential,
    ReplaceHealth,
    utc_clock,
)
from umbod.core.connectors.downstream_mcp.models import (
    ConnectorHealthy,
    StaticBearerConnectorDefinition,
    StaticBearerCredentialState,
    ToolCatalogSnapshot,
)
from umbod.core.connectors.downstream_mcp.personal_connections import (
    PersonalConnectionStore,
)
from umbod.core.connectors.downstream_mcp.personal_oauth_setup.ports import (
    PersonalOAuthSetupStore,
)
from umbod.core.connectors.downstream_mcp.stores import (
    CONNECTOR_CREDENTIAL_TABLE,
    CONNECTOR_DEFINITION_TABLE,
    CONNECTOR_HEALTH_TABLE,
    TOOL_CATALOG_TABLE,
    ConnectorDefinitionStore,
    ConnectorDefinitionStoreService,
    ConnectorHealthStore,
    ConnectorHealthStoreService,
    EncryptedCredentialStore,
    EncryptedCredentialStoreService,
    ToolCatalogStore,
    ToolCatalogStoreService,
)
from umbod.core.connectors.downstream_mcp.stores.personal_connections import (
    EncryptedPersonalConnectionStore,
)
from umbod.core.connectors.downstream_mcp.stores.personal_oauth_setup import (
    PersonalOAuthSetupStoreService,
)
from umbod.core.messaging.stores.event_stream import DatabaseEventStream
from umbod.core.persistence import Database
from umbod.core.publishing import ConnectorPublishingStore
from umbod.core.publishing.factories import create_connector_publishing_store


class AggregateHarness(Protocol):
    personal_oauth_setup: PersonalOAuthSetupStore
    unit_of_work: DownstreamConnectorUnitOfWork
    events: EventStream
    personal_connections: PersonalConnectionStore
    definitions: ConnectorDefinitionStore
    credentials: EncryptedCredentialStore
    catalogs: ToolCatalogStore
    health: ConnectorHealthStore
    publishing: ConnectorPublishingStore
    activations: ActivationStore


class Harness:
    def __init__(
        self,
        unit_of_work: DownstreamConnectorUnitOfWork,
        definitions: ConnectorDefinitionStore,
        credentials: EncryptedCredentialStore,
        catalogs: ToolCatalogStore,
        health: ConnectorHealthStore,
        publishing: ConnectorPublishingStore,
        activations: ActivationStore,
        personal_connections: PersonalConnectionStore,
        events: EventStream,
        personal_oauth_setup: PersonalOAuthSetupStore,
    ) -> None:
        self.personal_oauth_setup = personal_oauth_setup
        self.events = events
        self.unit_of_work = unit_of_work
        self.personal_connections = personal_connections
        self.definitions = definitions
        self.credentials = credentials
        self.catalogs = catalogs
        self.health = health
        self.publishing = publishing
        self.activations = activations


def _command() -> CreateDownstreamConnectorAggregate:
    checked_at = datetime(2026, 1, 2, tzinfo=UTC)
    return CreateDownstreamConnectorAggregate(
        definition=StaticBearerConnectorDefinition(
            connector_id="alpha",
            display_name="Alpha",
            capability_description="Manage downstream tools",
            endpoint_url="https://example.test/mcp",
        ),
        credential=ReplaceCredential(
            credential=StaticBearerCredentialState(
                connector_id="alpha", bearer_token="secret-token"
            )
        ),
        catalog=ReplaceCatalog(
            snapshot=ToolCatalogSnapshot(
                connector_id="alpha", discovered_at=checked_at, tools=()
            )
        ),
        health=ReplaceHealth(
            health=ConnectorHealthy(connector_id="alpha", checked_at=checked_at)
        ),
        activation=ReconcileActivation(operation_names=()),
        publication=PreservePublication(),
    )


async def _database_harness(
    database: Database, fault: Callable[[str], None]
) -> AggregateHarness:
    definitions = ConnectorDefinitionStoreService(database, CONNECTOR_DEFINITION_TABLE)
    credentials = EncryptedCredentialStoreService(
        database,
        CONNECTOR_CREDENTIAL_TABLE,
        AuthenticatedTextCipher("unit-of-work-secret"),
    )
    catalogs = ToolCatalogStoreService(database, TOOL_CATALOG_TABLE)
    health = ConnectorHealthStoreService(database, CONNECTOR_HEALTH_TABLE)
    activations = await create_capability_activation_store(database)
    publishing = await create_connector_publishing_store(database)
    return Harness(
        DownstreamConnectorUnitOfWorkService(
            database, AuthenticatedTextCipher("unit-of-work-secret"), fault, utc_clock
        ),
        definitions,
        credentials,
        catalogs,
        health,
        publishing,
        activations,
        EncryptedPersonalConnectionStore(
            database, AuthenticatedTextCipher("unit-of-work-secret")
        ),
        DatabaseEventStream(database),
        PersonalOAuthSetupStoreService(
            database, AuthenticatedTextCipher("unit-of-work-secret"), utc_clock
        ),
    )
