from typing import Callable, Literal, Protocol

from umbod.core.capabilities.tools.names import PublicToolIdentity
from umbod.core.connectors.downstream_mcp.personal_oauth_configuration import PersonalOAuthSettings
from umbod.core.connectors.downstream_mcp.models import (
    ConnectorDefinition,
    DiscoveryAdmission,
    ConnectorHealth,
    CredentialState,
    DomainModel,
    ToolCatalogSnapshot,
)


class KeepCredential(DomainModel):
    action: Literal["keep"] = "keep"


class ReplaceCredential(DomainModel):
    action: Literal["replace"] = "replace"
    credential: CredentialState


class DeleteCredential(DomainModel):
    action: Literal["delete"] = "delete"


CredentialMutation = KeepCredential | ReplaceCredential | DeleteCredential


class KeepCatalog(DomainModel):
    action: Literal["keep"] = "keep"


class ReplaceCatalog(DomainModel):
    action: Literal["replace"] = "replace"
    snapshot: ToolCatalogSnapshot


class DeleteCatalog(DomainModel):
    action: Literal["delete"] = "delete"


CatalogMutation = KeepCatalog | ReplaceCatalog | DeleteCatalog


class KeepHealth(DomainModel):
    action: Literal["keep"] = "keep"


class ReplaceHealth(DomainModel):
    action: Literal["replace"] = "replace"
    health: ConnectorHealth


class DeleteHealth(DomainModel):
    action: Literal["delete"] = "delete"


HealthMutation = KeepHealth | ReplaceHealth | DeleteHealth


class PreserveActivation(DomainModel):
    action: Literal["preserve"] = "preserve"


class ReconcileActivation(DomainModel):
    action: Literal["reconcile"] = "reconcile"
    operation_names: tuple[str, ...]


ActivationMutation = PreserveActivation | ReconcileActivation


class PreservePublication(DomainModel):
    action: Literal["preserve"] = "preserve"


class UnpublishConnector(DomainModel):
    action: Literal["unpublish"] = "unpublish"


class DeletePublication(DomainModel):
    action: Literal["delete"] = "delete"


PublicationMutation = PreservePublication | UnpublishConnector | DeletePublication


class CreateDownstreamConnectorAggregate(DomainModel):
    definition: ConnectorDefinition
    credential: ReplaceCredential | DeleteCredential
    catalog: ReplaceCatalog | DeleteCatalog
    health: ReplaceHealth | DeleteHealth
    activation: ReconcileActivation
    publication: PreservePublication | DeletePublication


class CreatePersonalOAuthConnectorAggregate(DomainModel):
    aggregate: CreateDownstreamConnectorAggregate
    configuration: PersonalOAuthSettings


class ReplaceDownstreamConnectorAggregate(DomainModel):
    native_identities: tuple[PublicToolIdentity, ...]
    definition: ConnectorDefinition
    credential: CredentialMutation
    catalog: CatalogMutation
    health: HealthMutation
    activation: ActivationMutation
    publication: PublicationMutation


class PublishDownstreamConnectorAggregate(DomainModel):
    connector_id: str
    native_identities: tuple[PublicToolIdentity, ...]


class UpdatePublishedConnectorPrefix(DomainModel):
    definition: ConnectorDefinition
    native_identities: tuple[PublicToolIdentity, ...]


class DeleteDownstreamConnectorAggregate(DomainModel):
    connector_id: str


class InvalidateDownstreamConnectorAggregate(DomainModel):
    connector_id: str
    health: ConnectorHealth


class ApplyDiscoveredCatalog(DomainModel):
    admission: DiscoveryAdmission
    native_identities: tuple[PublicToolIdentity, ...]
    connector_id: str
    catalog: ToolCatalogSnapshot | DeleteCatalog | KeepCatalog
    health: ConnectorHealth
    operation_names: tuple[str, ...]


class DownstreamConnectorUnitOfWork(Protocol):
    async def admit_discovery(self, connector_id: str) -> DiscoveryAdmission: ...

    async def create(self, command: CreateDownstreamConnectorAggregate) -> None: ...

    async def create_personal_oauth(self, command: CreatePersonalOAuthConnectorAggregate) -> None: ...

    async def replace(self, command: ReplaceDownstreamConnectorAggregate) -> None: ...

    async def publish(self, command: PublishDownstreamConnectorAggregate) -> bool: ...

    async def update_published_prefix(self, command: UpdatePublishedConnectorPrefix) -> None: ...

    async def delete(self, command: DeleteDownstreamConnectorAggregate) -> None: ...

    async def invalidate(self, command: InvalidateDownstreamConnectorAggregate) -> None: ...

    async def apply_discovery(self, command: ApplyDiscoveredCatalog) -> None: ...


DownstreamConnectorMutationFault = Callable[[str], None]


def no_downstream_connector_mutation_fault(phase: str) -> None:
    return None
