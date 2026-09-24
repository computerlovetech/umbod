import asyncio
from copy import deepcopy
from collections.abc import Awaitable, Callable
from typing import Any

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
    ReconcileActivation,
    ReplaceCatalog,
    ReplaceCredential,
    ReplaceDownstreamConnectorAggregate,
    ReplaceHealth,
    UnpublishConnector,
    UpdatePublishedConnectorPrefix,
)


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
    ) -> None:
        self._definitions = definitions
        self._credentials = credentials
        self._catalogs = catalogs
        self._health = health
        self._activations = activations
        self._publishing = publishing
        self._fault = fault
        self._lock = asyncio.Lock()

    async def create(self, command: CreateDownstreamConnectorAggregate) -> None:
        await self._atomic(lambda: self._replace(command))

    async def replace(self, command: ReplaceDownstreamConnectorAggregate) -> None:
        await self._atomic(lambda: self._replace(command))

    async def update_published_prefix(self, command: UpdatePublishedConnectorPrefix) -> None:
        async def mutate() -> None:
            identities = list(command.native_identities)
            for definition in (await self._definitions.list()).definitions:
                if not await self._publishing.is_published(definition.connector_id):
                    continue
                catalog = await self._catalogs.get(
                    ConnectorIdQuery(connector_id=definition.connector_id)
                )
                if not hasattr(catalog, "snapshot"):
                    continue
                prefix = (
                    command.definition.tool_name_prefix
                    if definition.connector_id == command.definition.connector_id
                    else definition.tool_name_prefix
                )
                identities.extend(
                    PublicToolIdentity(
                        connector_id=tool.identity.connector_id,
                        tool_name_prefix=prefix,
                        operation_name=tool.identity.downstream_name,
                    )
                    for tool in catalog.snapshot.tools
                )
            PublicToolNameValidator().validate_unique(tuple(identities))
            await self._replace(
                ReplaceDownstreamConnectorAggregate(
                    definition=command.definition,
                    credential=KeepCredential(),
                    catalog=KeepCatalog(),
                    health=KeepHealth(),
                    activation=PreserveActivation(),
                    publication=PreservePublication(),
                )
            )

        await self._atomic(mutate)

    async def delete(self, command: DeleteDownstreamConnectorAggregate) -> None:
        async def mutate() -> None:
            query = ConnectorIdQuery(connector_id=command.connector_id)
            self._phase("activation")
            await self._activations.reconcile("downstream_mcp", command.connector_id, "tool", ())
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

        await self._atomic(mutate)

    async def invalidate(self, command: InvalidateDownstreamConnectorAggregate) -> None:
        replacement = ReplaceDownstreamConnectorAggregate(
            definition=await self._definition(command.connector_id),
            credential=KeepCredential(),
            catalog=DeleteCatalog(),
            health=ReplaceHealth(health=command.health),
            activation=ReconcileActivation(operation_names=()),
            publication=UnpublishConnector(),
        )
        await self.replace(replacement)

    async def apply_discovery(self, command: ApplyDiscoveredCatalog) -> None:
        catalog = command.catalog
        replacement = ReplaceDownstreamConnectorAggregate(
            definition=await self._definition(command.connector_id),
            credential=KeepCredential(),
            catalog=DeleteCatalog()
            if isinstance(catalog, DeleteCatalog)
            else ReplaceCatalog(snapshot=catalog),
            health=ReplaceHealth(health=command.health),
            activation=ReconcileActivation(operation_names=command.operation_names),
            publication=PreservePublication(),
        )
        await self.replace(replacement)

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

    async def _definition(self, connector_id: str) -> Any:
        result = await self._definitions.get(ConnectorIdQuery(connector_id=connector_id))
        if not hasattr(result, "definition"):
            raise KeyError(connector_id)
        return result.definition

    def _phase(self, phase: str) -> None:
        self._fault(phase)

    async def _atomic(self, mutation: Callable[[], Awaitable[None]]) -> None:
        async with self._lock:
            await self._atomic_locked(mutation)

    async def _atomic_locked(self, mutation: Callable[[], Awaitable[None]]) -> None:
        targets = tuple(
            target
            for target in (
                self._definitions,
                self._credentials,
                self._catalogs,
                self._health,
                self._activations,
                self._publishing,
            )
            if hasattr(target, "__dict__")
        )
        states = tuple(deepcopy(target.__dict__) for target in targets)
        try:
            await mutation()
        except BaseException:
            for target, state in zip(targets, states, strict=True):
                target.__dict__.clear()
                target.__dict__.update(state)
            raise
