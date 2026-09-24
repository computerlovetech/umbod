from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from pydantic import TypeAdapter

from umbod.core.configuration.persistence import TextCipher
from umbod.core.publishing.stores.schema import (
    PUBLICATION_STATE_CONNECTOR_ID,
    PUBLICATION_STATE_TABLE,
    PublicationStateKey,
    PublicationStateRecord,
)
from umbod.core.capabilities.tools.names import PublicToolIdentity, PublicToolNameValidator
from umbod.core.activation.stores.schema import (
    CAPABILITY_ACTIVATION_STATE_CAPABILITY_KEY,
    CAPABILITY_ACTIVATION_STATE_CAPABILITY_KIND,
    CAPABILITY_ACTIVATION_STATE_CONNECTOR_ID,
    CAPABILITY_ACTIVATION_STATE_CONNECTOR_KIND,
    CAPABILITY_ACTIVATION_STATE_TABLE,
)
from umbod.core.connectors.downstream_mcp.models import ConnectorHealth, ToolCatalogSnapshot
from umbod.core.connectors.downstream_mcp.stores.catalogs import find_catalog_record, replace_catalog
from umbod.core.connectors.downstream_mcp.stores.credentials import save_credential
from umbod.core.connectors.downstream_mcp.stores.ports import (
    CONNECTOR_DEFINITION_ADAPTER,
    ReplaceToolCatalog,
    SaveCredential,
)
from umbod.core.connectors.downstream_mcp.stores.schema import (
    CONNECTOR_CREDENTIAL_CONNECTOR_ID,
    CONNECTOR_CREDENTIAL_TABLE,
    CONNECTOR_DEFINITION_CONNECTOR_ID,
    CONNECTOR_DEFINITION_TABLE,
    CONNECTOR_HEALTH_CONNECTOR_ID,
    CONNECTOR_HEALTH_TABLE,
    TOOL_CATALOG_CONNECTOR_ID,
    TOOL_CATALOG_TABLE,
    ConnectorDefinitionKey,
    ConnectorDefinitionRecord,
    ConnectorHealthKey,
    ConnectorHealthRecord,
)
from umbod.core.connectors.downstream_mcp.management.unit_of_work import (
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
    ReplaceCatalog,
    ReplaceCredential,
    ReplaceDownstreamConnectorAggregate,
    ReplaceHealth,
    UnpublishConnector,
    UpdatePublishedConnectorPrefix,
)
from umbod.core.invocation import (
    delete_connector_invocation_policies,
)
from umbod.core.persistence import (
    AllFields,
    AllOf,
    Database,
    DatabaseSession,
    DeleteQuery,
    Equals,
    NoFilter,
    Not,
    OneOf,
    Query,
    TransactionMode,
    Unordered,
    UpsertCommand,
)

Clock = Callable[[], datetime]
AggregateReplacement = CreateDownstreamConnectorAggregate | ReplaceDownstreamConnectorAggregate
_HEALTH_ADAPTER = TypeAdapter(ConnectorHealth)


@dataclass(frozen=True)
class MutationContext:
    cipher: TextCipher
    fault: DownstreamConnectorMutationFault
    clock: Clock


async def _publication(
    session: DatabaseSession, connector_id: str
) -> PublicationStateRecord | None:
    return await session.find_one(
        PUBLICATION_STATE_TABLE,
        Query(
            filter=Equals(PUBLICATION_STATE_CONNECTOR_ID, connector_id),
            projection=AllFields(),
            ordering=Unordered(),
        ),
    )


async def _delete_catalog(session: DatabaseSession, connector_id: str) -> None:
    await session.delete(
        TOOL_CATALOG_TABLE, DeleteQuery(Equals(TOOL_CATALOG_CONNECTOR_ID, connector_id))
    )


async def _write_health(
    session: DatabaseSession,
    health: ConnectorHealth,
    fault: DownstreamConnectorMutationFault,
) -> None:
    validated = _HEALTH_ADAPTER.validate_python(health)
    fault("health")
    await session.upsert(
        CONNECTOR_HEALTH_TABLE,
        UpsertCommand(
            key=ConnectorHealthKey(connector_id=validated.connector_id),
            row=ConnectorHealthRecord(
                connector_id=validated.connector_id,
                document=validated.model_dump(mode="json"),
            ),
        ),
    )


async def _reconcile_activation(
    session: DatabaseSession,
    connector_id: str,
    names: tuple[str, ...],
    fault: DownstreamConnectorMutationFault,
) -> None:
    fault("activation")
    predicate = AllOf(
        (
            Equals(CAPABILITY_ACTIVATION_STATE_CONNECTOR_KIND, "downstream_mcp"),
            Equals(CAPABILITY_ACTIVATION_STATE_CONNECTOR_ID, connector_id),
            Equals(CAPABILITY_ACTIVATION_STATE_CAPABILITY_KIND, "tool"),
        )
    )
    if names:
        predicate = AllOf(
            (predicate, Not(OneOf(CAPABILITY_ACTIVATION_STATE_CAPABILITY_KEY, names)))
        )
    await session.delete(CAPABILITY_ACTIVATION_STATE_TABLE, DeleteQuery(predicate))


async def _unpublish(
    session: DatabaseSession,
    connector_id: str,
    fault: DownstreamConnectorMutationFault,
    clock: Clock,
) -> None:
    fault("publication")
    current = await _publication(session, connector_id)
    if current is None:
        return
    await session.upsert(
        PUBLICATION_STATE_TABLE,
        UpsertCommand(
            key=PublicationStateKey(connector_id=connector_id),
            row=PublicationStateRecord(
                connector_id=connector_id,
                published=False,
                previously_published=current.published or current.previously_published,
                revision=current.revision + 1,
                updated_at=clock().isoformat(),
            ),
        ),
    )


async def _replace_definition(
    session: DatabaseSession,
    command: AggregateReplacement,
    fault: DownstreamConnectorMutationFault,
) -> None:
    definition = command.definition
    fault("definition")
    await session.upsert(
        CONNECTOR_DEFINITION_TABLE,
        UpsertCommand(
            key=ConnectorDefinitionKey(connector_id=definition.connector_id),
            row=ConnectorDefinitionRecord(
                connector_id=definition.connector_id,
                document=definition.model_dump(mode="json"),
                public_path=definition.public_path,
                capability_description=definition.capability_description,
            ),
        ),
    )


async def _replace_credential(
    session: DatabaseSession,
    command: AggregateReplacement,
    cipher: TextCipher,
    fault: DownstreamConnectorMutationFault,
) -> None:
    if isinstance(command.credential, KeepCredential):
        return
    fault("credential")
    if isinstance(command.credential, ReplaceCredential):
        await save_credential(
            session,
            CONNECTOR_CREDENTIAL_TABLE,
            cipher,
            SaveCredential(credential=command.credential.credential),
        )
    elif isinstance(command.credential, DeleteCredential):
        await session.delete(
            CONNECTOR_CREDENTIAL_TABLE,
            DeleteQuery(
                Equals(CONNECTOR_CREDENTIAL_CONNECTOR_ID, command.definition.connector_id)
            ),
        )


async def _replace_catalog(
    session: DatabaseSession,
    command: AggregateReplacement,
    fault: DownstreamConnectorMutationFault,
) -> None:
    if isinstance(command.catalog, KeepCatalog):
        return
    fault("catalog")
    if isinstance(command.catalog, ReplaceCatalog):
        await replace_catalog(
            session,
            TOOL_CATALOG_TABLE,
            ReplaceToolCatalog(snapshot=command.catalog.snapshot),
        )
    elif isinstance(command.catalog, DeleteCatalog):
        await _delete_catalog(session, command.definition.connector_id)


async def _replace_health(
    session: DatabaseSession,
    command: AggregateReplacement,
    fault: DownstreamConnectorMutationFault,
) -> None:
    if isinstance(command.health, ReplaceHealth):
        await _write_health(session, command.health.health, fault)
    elif isinstance(command.health, DeleteHealth):
        fault("health")
        await session.delete(
            CONNECTOR_HEALTH_TABLE,
            DeleteQuery(
                Equals(CONNECTOR_HEALTH_CONNECTOR_ID, command.definition.connector_id)
            ),
        )


async def _replace_activation(
    session: DatabaseSession,
    command: AggregateReplacement,
    fault: DownstreamConnectorMutationFault,
) -> None:
    if not isinstance(command.activation, PreserveActivation):
        await _reconcile_activation(
            session,
            command.definition.connector_id,
            command.activation.operation_names,
            fault,
        )


async def _replace_publication(
    session: DatabaseSession,
    command: AggregateReplacement,
    fault: DownstreamConnectorMutationFault,
    clock: Clock,
) -> None:
    if isinstance(command.publication, UnpublishConnector):
        await _unpublish(session, command.definition.connector_id, fault, clock)
    elif isinstance(command.publication, DeletePublication):
        fault("publication")
        await session.delete(
            PUBLICATION_STATE_TABLE,
            DeleteQuery(
                Equals(PUBLICATION_STATE_CONNECTOR_ID, command.definition.connector_id)
            ),
        )


async def _replace(
    session: DatabaseSession,
    command: AggregateReplacement,
    context: MutationContext,
) -> None:
    await _replace_definition(session, command, context.fault)
    await _replace_credential(session, command, context.cipher, context.fault)
    await _replace_catalog(session, command, context.fault)
    if not isinstance(command.health, KeepHealth):
        await _replace_health(session, command, context.fault)
    await _replace_activation(session, command, context.fault)
    if not isinstance(command.publication, PreservePublication):
        await _replace_publication(session, command, context.fault, context.clock)


async def _published_identities(
    session: DatabaseSession, command: UpdatePublishedConnectorPrefix
) -> list[PublicToolIdentity]:
    identities = list(command.native_identities)
    definitions = await session.find_many(
        CONNECTOR_DEFINITION_TABLE,
        Query(filter=NoFilter(), projection=AllFields(), ordering=Unordered()),
    )
    for record in definitions:
        publication = await _publication(session, record.connector_id)
        if publication is None or not publication.published:
            continue
        catalog = await find_catalog_record(session, TOOL_CATALOG_TABLE, record.connector_id)
        if catalog is None:
            continue
        definition = CONNECTOR_DEFINITION_ADAPTER.validate_python(record.document)
        snapshot = ToolCatalogSnapshot.model_validate(catalog.snapshot)
        prefix = command.definition.tool_name_prefix if (
            definition.connector_id == command.definition.connector_id
        ) else definition.tool_name_prefix
        identities.extend(
            PublicToolIdentity(
                connector_id=tool.identity.connector_id,
                tool_name_prefix=prefix,
                operation_name=tool.identity.downstream_name,
            )
            for tool in snapshot.tools
        )
    return identities


async def _update_published_prefix(
    session: DatabaseSession,
    command: UpdatePublishedConnectorPrefix,
    context: MutationContext,
) -> None:
    PublicToolNameValidator().validate_unique(tuple(await _published_identities(session, command)))
    replacement = ReplaceDownstreamConnectorAggregate(
        definition=command.definition,
        credential=KeepCredential(),
        catalog=KeepCatalog(),
        health=KeepHealth(),
        activation=PreserveActivation(),
        publication=PreservePublication(),
    )
    await _replace(session, replacement, context)


async def _delete(
    session: DatabaseSession,
    command: DeleteDownstreamConnectorAggregate,
    fault: DownstreamConnectorMutationFault,
) -> None:
    await delete_connector_invocation_policies(session, "downstream_mcp", command.connector_id)
    for phase, table, field in (
        ("activation", CAPABILITY_ACTIVATION_STATE_TABLE, CAPABILITY_ACTIVATION_STATE_CONNECTOR_ID),
        ("credential", CONNECTOR_CREDENTIAL_TABLE, CONNECTOR_CREDENTIAL_CONNECTOR_ID),
        ("catalog", TOOL_CATALOG_TABLE, TOOL_CATALOG_CONNECTOR_ID),
        ("health", CONNECTOR_HEALTH_TABLE, CONNECTOR_HEALTH_CONNECTOR_ID),
        ("definition", CONNECTOR_DEFINITION_TABLE, CONNECTOR_DEFINITION_CONNECTOR_ID),
        ("publication", PUBLICATION_STATE_TABLE, PUBLICATION_STATE_CONNECTOR_ID),
    ):
        fault(phase)
        await session.delete(table, DeleteQuery(Equals(field, command.connector_id)))


class DownstreamConnectorUnitOfWorkService:
    def __init__(
        self,
        database: Database,
        cipher: TextCipher,
        fault: DownstreamConnectorMutationFault,
        clock: Clock,
    ) -> None:
        self._database = database
        self._context = MutationContext(cipher=cipher, fault=fault, clock=clock)

    async def create(self, command: CreateDownstreamConnectorAggregate) -> None:
        await self._run(lambda session: _replace(session, command, self._context))

    async def replace(self, command: ReplaceDownstreamConnectorAggregate) -> None:
        await self._run(lambda session: _replace(session, command, self._context))

    async def update_published_prefix(self, command: UpdatePublishedConnectorPrefix) -> None:
        await self._run(
            lambda session: _update_published_prefix(session, command, self._context)
        )

    async def delete(self, command: DeleteDownstreamConnectorAggregate) -> None:
        await self._run(lambda session: _delete(session, command, self._context.fault))

    async def invalidate(self, command: InvalidateDownstreamConnectorAggregate) -> None:
        async def mutate(session: DatabaseSession) -> None:
            self._context.fault("catalog")
            await _delete_catalog(session, command.connector_id)
            await _write_health(session, command.health, self._context.fault)
            await _reconcile_activation(session, command.connector_id, (), self._context.fault)
            await _unpublish(
                session, command.connector_id, self._context.fault, self._context.clock
            )

        await self._run(mutate)

    async def apply_discovery(self, command: ApplyDiscoveredCatalog) -> None:
        async def mutate(session: DatabaseSession) -> None:
            self._context.fault("catalog")
            if isinstance(command.catalog, DeleteCatalog):
                await _delete_catalog(session, command.connector_id)
            else:
                await replace_catalog(
                    session,
                    TOOL_CATALOG_TABLE,
                    ReplaceToolCatalog(snapshot=command.catalog),
                )
            await _write_health(session, command.health, self._context.fault)
            await _reconcile_activation(
                session, command.connector_id, command.operation_names, self._context.fault
            )

        await self._run(mutate)

    async def _run(self, mutation: Callable[[DatabaseSession], Awaitable[None]]) -> None:
        async with self._database.session(mode=TransactionMode.SERIALIZED_WRITE) as session:
            await mutation(session)


def utc_clock() -> datetime:
    return datetime.now(UTC)
