from umbod.core.connectors.downstream_mcp.management.discovery_admission import catalog_revision
from umbod.core.connectors.downstream_mcp.models import DiscoveryAdmission, ToolCatalogSnapshot, MissingCatalogRevision, PresentCatalogRevision
from umbod.core.connectors.downstream_mcp.stores.ports import CredentialFound
from umbod.core.connectors.downstream_mcp.errors import ObsoleteDownstreamCatalogError
from messaging.ports import EventStream
from umbod.core.publishing.events import connector_publication_changed_event
from umbod.core.messaging.discovery_events import connector_discovery_changed_event
import asyncio

from ..personal_tools import PersonalToolAccessStore, PersonalToolPolicyStore

from umbod.core.connectors.downstream_mcp.personal_oauth_configuration import PersonalOAuthConfigurationStore, ReplacePersonalOAuthConfiguration
from umbod.core.connectors.downstream_mcp.management.unit_of_work import CreatePersonalOAuthConnectorAggregate

from umbod.core.connectors.downstream_mcp.personal_connections import PersonalConnectionStore
from copy import deepcopy
from collections.abc import Awaitable, Callable
from typing import TypeVar

from umbod.core.connectors.downstream_mcp.errors import DownstreamConnectorNotFoundError, DownstreamConnectorUnavailableError
from umbod.core.connectors.downstream_mcp.models import ConnectorDefinition, uses_personal_oauth
from umbod.core.connectors.downstream_mcp.stores.ports import ConnectorDefinitionFound, ToolCatalogFound
from umbod.core.publishing import ConnectorPublishingStore
from umbod.core.capabilities.tools.names import PublicToolIdentity, PublicToolNameValidator
from umbod.core.activation import ActivationStore
from umbod.core.connectors.downstream_mcp.stores import (
    ConnectorDefinitionStore,
    ConnectorHealthStore,
    ConnectorIdQuery,
    EncryptedCredentialStore,
    ReplaceToolCatalog,
    SaveConnectorDefinition,
    SaveConnectorHealth,
    SaveCredential,
    ToolCatalogStore,
)
from umbod.core.connectors.downstream_mcp.management import (
    ApplyDiscoveredCatalog,
    CreateDownstreamConnectorAggregate,
    DeleteCatalog,
    DeleteCredential,
    DeleteDownstreamConnectorAggregate,
    DeleteHealth,
    DeletePublication,
    DownstreamConnectorMutationFault,
    InvalidateDownstreamConnectorAggregate,
    KeepCatalog,
    KeepCredential,
    KeepHealth,
    PreserveActivation,
    PreservePublication,
    PublishDownstreamConnectorAggregate,
    ReconcileActivation,
    ReplaceCatalog,
    ReplaceCredential,
    ReplaceDownstreamConnectorAggregate,
    ReplaceHealth,
    UnpublishConnector,
    UpdatePublishedConnectorPrefix,
)


MutationResult = TypeVar("MutationResult")


class InMemoryDownstreamConnectorUnitOfWork:
    def __init__(
        self,
        definitions: ConnectorDefinitionStore,
        credentials: EncryptedCredentialStore,
        catalogs: ToolCatalogStore,
        health: ConnectorHealthStore,
        activations: ActivationStore,
        publishing: ConnectorPublishingStore,
        fault: DownstreamConnectorMutationFault,
        personal_connections: PersonalConnectionStore,
        personal_oauth_configurations: PersonalOAuthConfigurationStore,
        personal_tool_policies: PersonalToolPolicyStore,
        personal_tool_access: PersonalToolAccessStore,
        events: EventStream,
    ) -> None:
        self._events = events
        self._definitions = definitions
        self._credentials = credentials
        self._catalogs = catalogs
        self._health = health
        self._activations = activations
        self._publishing = publishing
        self._fault = fault
        self._personal_connections = personal_connections
        self._personal_oauth_configurations = personal_oauth_configurations
        self._personal_tool_policies = personal_tool_policies
        self._personal_tool_access = personal_tool_access
        self._lock = asyncio.Lock()
        self._discovery_revisions: dict[str, int] = {}

    async def _admit_discovery(self, connector_id: str) -> DiscoveryAdmission:
        definition = await self._definition(connector_id)
        credential = await self._credentials.get(ConnectorIdQuery(connector_id=connector_id))
        if not isinstance(credential, CredentialFound):
            raise DownstreamConnectorUnavailableError(connector_id)
        catalog = await self._catalogs.get(ConnectorIdQuery(connector_id=connector_id))
        return DiscoveryAdmission(
            definition=definition, credential=credential.credential,
            aggregate_revision=self._discovery_revisions.get(connector_id, 0),
            catalog_revision=PresentCatalogRevision(state="present", fingerprint=catalog_revision(catalog.snapshot)) if isinstance(catalog, ToolCatalogFound) else MissingCatalogRevision(state="missing"),
        )

    async def admit_discovery(self, connector_id: str) -> DiscoveryAdmission:
        async with self._lock:
            return await self._admit_discovery(connector_id)

    async def create(self, command: CreateDownstreamConnectorAggregate) -> None:
        await self._atomic(lambda: self._replace(command), command.definition.connector_id)

    async def create_personal_oauth(self, command: CreatePersonalOAuthConnectorAggregate) -> None:
        async def mutate() -> None:
            await self._replace(command.aggregate)
            self._phase("personal_oauth_configuration")
            await self._personal_oauth_configurations.replace(ReplacePersonalOAuthConfiguration(
                connector_id=command.aggregate.definition.connector_id,
                expected_revision="legacy", settings=command.configuration,
            ))
            self._phase("personal_oauth_configuration_saved")

        await self._atomic(mutate, command.aggregate.definition.connector_id)

    async def replace(self, command: ReplaceDownstreamConnectorAggregate) -> None:
        await self._atomic(lambda: self._replace(command), command.definition.connector_id)

    async def publish(self, command: PublishDownstreamConnectorAggregate) -> bool:
        async def mutate() -> bool:
            definition = await self._definition(command.connector_id)
            if await self._publishing.is_published(command.connector_id):
                return False
            catalog = await self._catalogs.get(ConnectorIdQuery(connector_id=command.connector_id))
            if not uses_personal_oauth(definition):
                if not isinstance(catalog, ToolCatalogFound) or not any((
                    catalog.snapshot.tools, catalog.snapshot.prompts,
                    catalog.snapshot.resources, catalog.snapshot.resource_templates,
                )):
                    raise DownstreamConnectorUnavailableError(command.connector_id)
            await self._validate_namespace(definition, command.native_identities, True)
            self._phase("publication")
            await self._publishing.publish_connector(command.connector_id)
            self._phase("event")
            await self._events.append(connector_publication_changed_event(command.connector_id, "published"))
            return True

        async with self._lock:
            return await self._atomic_locked(mutate)

    async def _validate_namespace(
        self,
        candidate: ConnectorDefinition,
        native_identities: tuple[PublicToolIdentity, ...],
        include_candidate: bool,
    ) -> None:
        identities = list(native_identities)
        for definition in (await self._definitions.list()).definitions:
            is_candidate = definition.connector_id == candidate.connector_id
            if not (include_candidate and is_candidate) and not await self._publishing.is_published(definition.connector_id):
                continue
            catalog = await self._catalogs.get(ConnectorIdQuery(connector_id=definition.connector_id))
            if not isinstance(catalog, ToolCatalogFound):
                continue
            prefix = candidate.tool_name_prefix if is_candidate else definition.tool_name_prefix
            identities.extend(
                PublicToolIdentity(
                    connector_id=definition.connector_id,
                    tool_name_prefix=prefix,
                    operation_name=tool.identity.downstream_name,
                )
                for tool in catalog.snapshot.tools
            )
        PublicToolNameValidator().validate_unique(tuple(identities))

    async def update_published_prefix(self, command: UpdatePublishedConnectorPrefix) -> None:
        async def mutate() -> None:
            await self._validate_namespace(command.definition, command.native_identities, False)
            await self._replace(
                ReplaceDownstreamConnectorAggregate(
                    native_identities=command.native_identities,
                    definition=command.definition,
                    credential=KeepCredential(),
                    catalog=KeepCatalog(),
                    health=KeepHealth(),
                    activation=PreserveActivation(),
                    publication=PreservePublication(),
                )
            )

        await self._atomic(mutate, command.definition.connector_id)

    async def delete(self, command: DeleteDownstreamConnectorAggregate) -> None:
        async def mutate() -> None:
            query = ConnectorIdQuery(connector_id=command.connector_id)
            self._phase("activation")
            await self._activations.reconcile("downstream_mcp", command.connector_id, "tool", ())
            self._phase("personal_tool_policy")
            await self._personal_tool_policies.delete_connector(command.connector_id)
            self._phase("personal_tool_observations")
            self._phase("personal_oauth_configuration")
            await self._personal_oauth_configurations.delete_connector(command.connector_id)
            self._phase("personal_connections")
            await self._personal_connections.delete_connector(command.connector_id)
            self._phase("credential")
            await self._credentials.delete(query)
            self._phase("catalog")
            await self._catalogs.delete(query)
            self._phase("health")
            await self._health.delete(query)
            self._phase("definition")
            await self._definitions.delete(query)
            self._phase("publication")
            await self._publishing.delete_connector(command.connector_id)

        await self._atomic(mutate, command.connector_id)

    async def invalidate(self, command: InvalidateDownstreamConnectorAggregate) -> None:
        async def mutate() -> None:
            await self._replace(ReplaceDownstreamConnectorAggregate(
                native_identities=(),
                definition=await self._definition(command.connector_id),
                credential=KeepCredential(),
                catalog=DeleteCatalog(),
                health=ReplaceHealth(health=command.health),
                activation=PreserveActivation(),
                publication=UnpublishConnector(),
            ))

        await self._atomic(mutate, command.connector_id)

    async def apply_discovery(self, command: ApplyDiscoveredCatalog) -> None:
        async def mutate() -> None:
            try:
                current = await self._admit_discovery(command.connector_id)
            except (DownstreamConnectorNotFoundError, DownstreamConnectorUnavailableError) as error:
                raise ObsoleteDownstreamCatalogError(command.connector_id) from error
            if current != command.admission:
                raise ObsoleteDownstreamCatalogError(command.connector_id)
            catalog = command.catalog
            await self._replace(ReplaceDownstreamConnectorAggregate(
                native_identities=command.native_identities,
                definition=await self._definition(command.connector_id),
                credential=KeepCredential(),
                catalog=ReplaceCatalog(snapshot=catalog) if isinstance(catalog, ToolCatalogSnapshot) else catalog,
                health=ReplaceHealth(health=command.health),
                activation=ReconcileActivation(operation_names=command.operation_names)
                if isinstance(catalog, ToolCatalogSnapshot) else PreserveActivation(),
                publication=PreservePublication(),
            ))
            if isinstance(catalog, ToolCatalogSnapshot):
                for kind, names in (
                    ("prompt", tuple(prompt.name for prompt in catalog.prompts)),
                    ("resource", tuple(resource.uri for resource in catalog.resources)),
                    ("resource_template", tuple(template.uri_template for template in catalog.resource_templates)),
                ):
                    await self._activations.reconcile("downstream_mcp", command.connector_id, kind, names)

        await self._atomic(mutate, command.connector_id)

    async def _replace(
        self, command: CreateDownstreamConnectorAggregate | ReplaceDownstreamConnectorAggregate
    ) -> None:
        query = ConnectorIdQuery(connector_id=command.definition.connector_id)
        self._phase("definition")
        await self._definitions.save(SaveConnectorDefinition(definition=command.definition))
        if not isinstance(command.credential, KeepCredential):
            self._phase("credential")
            if isinstance(command.credential, ReplaceCredential):
                await self._credentials.save(
                    SaveCredential(credential=command.credential.credential)
                )
            elif isinstance(command.credential, DeleteCredential):
                await self._credentials.delete(query)
        if not isinstance(command.catalog, KeepCatalog):
            self._phase("catalog")
            if isinstance(command.catalog, ReplaceCatalog):
                await self._catalogs.replace(ReplaceToolCatalog(snapshot=command.catalog.snapshot))
            elif isinstance(command.catalog, DeleteCatalog):
                await self._catalogs.delete(query)
        if not isinstance(command.health, KeepHealth):
            self._phase("health")
            if isinstance(command.health, ReplaceHealth):
                await self._health.save(SaveConnectorHealth(health=command.health.health))
            elif isinstance(command.health, DeleteHealth):
                await self._health.delete(query)
        if not isinstance(command.activation, PreserveActivation):
            self._phase("activation")
            await self._activations.reconcile(
                "downstream_mcp", command.definition.connector_id, "tool", command.activation.operation_names
            )
        if not isinstance(command.publication, PreservePublication):
            self._phase("publication")
            if isinstance(command.publication, UnpublishConnector):
                await self._publishing.unpublish_connector(command.definition.connector_id)
            elif isinstance(command.publication, DeletePublication):
                await self._publishing.delete_connector(command.definition.connector_id)

        if isinstance(command, ReplaceDownstreamConnectorAggregate):
            await self._validate_namespace(command.definition, command.native_identities, False)

    async def _definition(self, connector_id: str) -> ConnectorDefinition:
        result = await self._definitions.get(ConnectorIdQuery(connector_id=connector_id))
        if not isinstance(result, ConnectorDefinitionFound):
            raise DownstreamConnectorNotFoundError(connector_id)
        return result.definition

    def _phase(self, phase: str) -> None:
        self._fault(phase)

    async def _atomic(self, mutation: Callable[[], Awaitable[MutationResult]], connector_id: str) -> MutationResult:
        async def mutate_and_publish() -> MutationResult:
            result = await mutation()
            self._phase("event")
            await self._events.append(connector_discovery_changed_event("downstream_mcp", connector_id))
            return result

        async with self._lock:
            result = await self._atomic_locked(mutate_and_publish)
            self._discovery_revisions[connector_id] = self._discovery_revisions.get(connector_id, 0) + 1
            return result

    async def _atomic_locked(self, mutation: Callable[[], Awaitable[MutationResult]]) -> MutationResult:
        targets = tuple(
            target
            for target in (
                self._events,
                self._personal_connections,
                self._personal_oauth_configurations,
                self._personal_tool_policies,
                self._personal_tool_access,
                self._definitions,
                self._credentials,
                self._catalogs,
                self._health,
                self._activations,
                self._publishing,
            )
            if hasattr(target, "__dict__")
        )
        states = deepcopy(tuple(target.__dict__ for target in targets))
        try:
            return await mutation()
        except BaseException:
            for target, state in zip(targets, states, strict=True):
                target.__dict__.clear()
                target.__dict__.update(state)
            raise
