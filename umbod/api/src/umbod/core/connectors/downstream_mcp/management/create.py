from umbod.core.identity import ConnectorIdentity
from umbod.core.connectors.downstream_mcp.errors import (
    DownstreamConnectorConflictError,
    DownstreamPublicPathConflictError,
)
from umbod.core.connectors.downstream_mcp.models import (
    ConnectorDefinition,
    CreateConnectorDefinition,
    PreparedCatalogConnector,
)
from umbod.core.connectors.downstream_mcp.management.ports import (
    ConnectorIdentityAvailability,
    DownstreamConnectorIdGenerator,
)
from umbod.core.connectors.downstream_mcp.management.preparation import DownstreamConnectorPreparation
from umbod.core.connectors.downstream_mcp.management.unit_of_work import (
    CreateDownstreamConnectorAggregate,
    DeleteCatalog,
    DeleteCredential,
    DeleteHealth,
    DownstreamConnectorUnitOfWork,
    PreservePublication,
    ReconcileActivation,
    ReplaceCatalog,
    ReplaceCredential,
    ReplaceHealth,
)
from umbod.core.connectors.downstream_mcp.stores.ports import (
    ConnectorDefinitionFound,
    ConnectorDefinitionMissing,
    ConnectorDefinitionStore,
    ConnectorIdQuery,
    PublicPathQuery,
)


class DownstreamConnectorCreator:
    def __init__(
        self,
        definitions: ConnectorDefinitionStore,
        ids: DownstreamConnectorIdGenerator,
        identities: ConnectorIdentityAvailability,
        preparation: DownstreamConnectorPreparation,
        unit_of_work: DownstreamConnectorUnitOfWork,
    ) -> None:
        self._definitions = definitions
        self._ids = ids
        self._identities = identities
        self._preparation = preparation
        self._unit_of_work = unit_of_work

    async def create(self, request: CreateConnectorDefinition) -> ConnectorDefinition:
        connector_id = self._ids.new_id()
        await self._ensure_identity_available(connector_id)
        prepared = await self._preparation.prepare_create(connector_id, request)
        await self._ensure_public_path_available(prepared.definition)
        await self._unit_of_work.create(self._aggregate(prepared))
        return prepared.definition

    async def _ensure_identity_available(self, connector_id: str) -> None:
        await self._identities.ensure_available(
            ConnectorIdentity(connector_id=connector_id, connector_type="downstream_mcp")
        )
        result = await self._definitions.get(ConnectorIdQuery(connector_id=connector_id))
        if not isinstance(result, ConnectorDefinitionMissing):
            raise DownstreamConnectorConflictError(connector_id)

    async def _ensure_public_path_available(self, definition: ConnectorDefinition) -> None:
        result = await self._definitions.get_by_public_path(
            PublicPathQuery(public_path=definition.public_path)
        )
        if isinstance(result, ConnectorDefinitionFound):
            raise DownstreamPublicPathConflictError(definition.public_path)

    @staticmethod
    def _aggregate(prepared: object) -> CreateDownstreamConnectorAggregate:
        if isinstance(prepared, PreparedCatalogConnector):
            operation_names = tuple(
                tool.identity.downstream_name for tool in prepared.snapshot.tools
            )
            return CreateDownstreamConnectorAggregate(
                definition=prepared.definition,
                credential=ReplaceCredential(credential=prepared.credential),
                catalog=ReplaceCatalog(snapshot=prepared.snapshot),
                health=ReplaceHealth(health=prepared.health),
                activation=ReconcileActivation(operation_names=operation_names),
                publication=PreservePublication(),
            )
        return CreateDownstreamConnectorAggregate(
            definition=prepared.definition,
            credential=DeleteCredential(),
            catalog=DeleteCatalog(),
            health=DeleteHealth(),
            activation=ReconcileActivation(operation_names=()),
            publication=PreservePublication(),
        )
