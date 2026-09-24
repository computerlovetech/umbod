
from umbod.core.configuration.events import connector_configuration_changed_event
from pydantic import SecretStr
from umbod.core.publishing.events import connector_publication_changed_event
from umbod.core.publishing import ConnectorPublishingStore
from umbod.core.capabilities.tools.names import PublicToolIdentity, PublicToolIdentitySource, PublicToolNameValidator
from umbod.core.connectors.downstream_mcp.models import (
    ConnectorDefinition,
    CredentialState,
    NoAuthConnectorDefinition,
    NoAuthCredentialState,
    OAuthConnectorDefinition,
    OAuthCredentialState,
    PreparedCatalogConnector,
    StaticBearerConnectorDefinition,
    StaticBearerCredentialState,
)
from umbod.core.connectors.downstream_mcp.management.preparation import DownstreamConnectorPreparation
from umbod.core.connectors.downstream_mcp.management.queries import DownstreamConnectorQueries
from umbod.core.connectors.downstream_mcp.management.unit_of_work import (
    DownstreamConnectorUnitOfWork,
    PreserveActivation,
    PreservePublication,
    ReconcileActivation,
    ReplaceCatalog,
    ReplaceCredential,
    ReplaceDownstreamConnectorAggregate,
    ReplaceHealth,
    UnpublishConnector,
    UpdatePublishedConnectorPrefix,
)
from umbod.core.connectors.downstream_mcp.stores.ports import (
    ConnectorIdQuery,
    CredentialFound,
    EncryptedCredentialStore,
    ToolCatalogFound,
    ToolCatalogStore,
)
from messaging.ports import EventStream


class DownstreamConnectorUpdater:
    def __init__(
        self,
        credentials: EncryptedCredentialStore,
        catalogs: ToolCatalogStore,
        publishing: ConnectorPublishingStore,
        events: EventStream,
        unit_of_work: DownstreamConnectorUnitOfWork,
        preparation: DownstreamConnectorPreparation,
        queries: DownstreamConnectorQueries,
        tool_name_validator: PublicToolNameValidator,
        identity_source: PublicToolIdentitySource,
    ) -> None:
        self._credentials = credentials
        self._catalogs = catalogs
        self._publishing = publishing
        self._events = events
        self._unit_of_work = unit_of_work
        self._preparation = preparation
        self._queries = queries
        self._tool_name_validator = tool_name_validator
        self._identity_source = identity_source

    async def update(
        self, current: ConnectorDefinition, definition: ConnectorDefinition, replacement_token: str
    ) -> ConnectorDefinition:
        if (
            current.tool_name_prefix != definition.tool_name_prefix
            and await self._publishing.is_published(definition.connector_id)
        ):
            identities = await self._published_identities_with_candidate(definition)
            self._tool_name_validator.validate_unique(identities)
        if self._is_prefix_only_change(current, definition, replacement_token):
            await self._update_prefix(definition)
            return definition
        query = ConnectorIdQuery(connector_id=definition.connector_id)
        existing = await self._credentials.get(query)
        catalog = await self._catalogs.get(query)
        was_published = await self._publishing.is_published(definition.connector_id)
        prepared, credential_mutation = await self._prepare_configuration(
            current,
            definition,
            existing,
            replacement_token,
        )
        definition = prepared.definition
        configuration_changed = (
            current.endpoint_url != definition.endpoint_url
            or current.auth_type != definition.auth_type
            or self._header_configuration(current) != self._header_configuration(definition)
            or bool(replacement_token)
        )
        await self._replace(prepared, credential_mutation, configuration_changed)
        await self._emit_events(
            definition.connector_id, configuration_changed, was_published, catalog
        )
        return definition

    @staticmethod
    def _header_configuration(definition: ConnectorDefinition) -> tuple[str, str | None]:
        if isinstance(definition, StaticBearerConnectorDefinition):
            return definition.header_type, definition.custom_header_name
        return "bearer", None

    @staticmethod
    def _is_prefix_only_change(
        current: ConnectorDefinition, definition: ConnectorDefinition, replacement_token: str
    ) -> bool:
        return (
            not replacement_token
            and current.tool_name_prefix != definition.tool_name_prefix
            and current.model_copy(update={"tool_name_prefix": definition.tool_name_prefix})
            == definition
        )

    async def _update_prefix(self, definition: ConnectorDefinition) -> None:
        await self._unit_of_work.update_published_prefix(
            UpdatePublishedConnectorPrefix(
                definition=definition,
                native_identities=await self._identity_source.identities(),
            )
        )

    async def _published_identities_with_candidate(
        self, candidate: ConnectorDefinition
    ) -> tuple[PublicToolIdentity, ...]:
        identities = list(await self._identity_source.identities())
        for published in (await self._queries.list()).definitions:
            if not await self._publishing.is_published(published.connector_id):
                continue
            catalog = await self._queries.catalog(published.connector_id)
            if not isinstance(catalog, ToolCatalogFound):
                continue
            prefix = (
                candidate.tool_name_prefix
                if published.connector_id == candidate.connector_id
                else published.tool_name_prefix
            )
            identities.extend(
                PublicToolIdentity(
                    connector_id=tool.identity.connector_id,
                    tool_name_prefix=prefix,
                    operation_name=tool.identity.downstream_name,
                )
                for tool in catalog.snapshot.tools
            )
        return tuple(identities)

    async def _prepare_configuration(
        self,
        current: ConnectorDefinition,
        definition: ConnectorDefinition,
        existing: object,
        replacement_token: str,
    ) -> tuple[
        PreparedCatalogConnector,
        ReplaceCredential,
    ]:
        credential = self._resolve_credential(current, definition, existing, replacement_token)
        self._validate_pair(definition, credential)
        prepared = await self._preparation.prepare_update(definition, credential)
        return prepared, ReplaceCredential(credential=prepared.credential)

    async def reauthorize(self, connector_id: str, authorization: SecretStr) -> ConnectorDefinition:
        current = await self._queries.get(connector_id)
        if not isinstance(current, OAuthConnectorDefinition):
            raise ValueError("Only OAuth connections can be signed in again.")
        prepared = await self._preparation.prepare_update(current, OAuthCredentialState(
            connector_id=connector_id, authorization=authorization
        ))
        await self._replace(prepared, ReplaceCredential(credential=prepared.credential), False)
        await self._events.append(connector_configuration_changed_event(connector_id))
        return prepared.definition

    async def _replace(
        self,
        prepared: PreparedCatalogConnector,
        credential_mutation: ReplaceCredential,
        configuration_changed: bool,
    ) -> None:
        catalog_mutation = ReplaceCatalog(snapshot=prepared.snapshot)
        health_mutation = ReplaceHealth(health=prepared.health)
        activation_mutation = ReconcileActivation(
            operation_names=tuple(
                tool.identity.downstream_name for tool in prepared.snapshot.tools
            )
        )
        aggregate = ReplaceDownstreamConnectorAggregate(
            definition=prepared.definition,
            credential=credential_mutation,
            catalog=catalog_mutation,
            health=health_mutation,
            activation=activation_mutation if configuration_changed else PreserveActivation(),
            publication=UnpublishConnector() if configuration_changed else PreservePublication(),
        )
        await self._unit_of_work.replace(aggregate)

    async def _emit_events(
        self,
        connector_id: str,
        configuration_changed: bool,
        was_published: bool,
        catalog: object,
    ) -> None:
        if not configuration_changed:
            return
        if was_published and isinstance(catalog, ToolCatalogFound):
            await self._events.append(
                connector_publication_changed_event(connector_id, "unpublished")
            )
        await self._events.append(connector_configuration_changed_event(connector_id))

    def _resolve_credential(
        self,
        current: ConnectorDefinition,
        definition: ConnectorDefinition,
        existing: object,
        replacement_token: str,
    ) -> CredentialState:
        if isinstance(definition, NoAuthConnectorDefinition):
            return NoAuthCredentialState(connector_id=definition.connector_id)
        if isinstance(definition, OAuthConnectorDefinition):
            if (replacement_token or current.endpoint_url != definition.endpoint_url
                or not isinstance(existing, CredentialFound)
                or not isinstance(existing.credential, OAuthCredentialState)):
                raise ValueError("Sign in again before changing an OAuth connection's server.")
            return existing.credential
        if replacement_token:
            return StaticBearerCredentialState(
                connector_id=definition.connector_id, bearer_token=replacement_token
            )
        if (
            not isinstance(current, StaticBearerConnectorDefinition)
            or not isinstance(existing, CredentialFound)
            or not isinstance(existing.credential, StaticBearerCredentialState)
        ):
            raise ValueError("bearer token is required")
        return existing.credential

    def _validate_pair(self, definition: ConnectorDefinition, credential: CredentialState) -> None:
        if (
            definition.connector_id != credential.connector_id
            or definition.auth_type != credential.auth_type
        ):
            raise ValueError("connector authentication configuration does not match credential")
