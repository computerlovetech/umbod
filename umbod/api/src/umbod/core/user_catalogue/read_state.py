from dataclasses import dataclass

from umbod.core.activation.domain import CapabilityActivationReader
from umbod.core.activation.stores.reads import ActivationReadState, plan_activation_reads
from umbod.core.activation.stores.schema import CapabilityActivationStateRecord
from umbod.core.permissions.ports import GroupPermissionLookup
from umbod.core.permissions.stores.reads import (
    PermissionReadState,
    plan_capability_permission_reads,
    plan_connector_permission_reads,
)
from umbod.core.permissions.stores.schema import (
    GroupCapabilityPermissionRecord,
    GroupConnectorPermissionRecord,
)
from umbod.core.persistence.plan import ManyRead, ReadPlanOperations, ReadResults
from umbod.core.publishing.store import ConnectorPublicationReader
from umbod.core.publishing.stores.reads import PublicationReadState, plan_publication_reads
from umbod.core.publishing.stores.schema import PublicationStateRecord


@dataclass(frozen=True)
class CatalogueReadState:
    publishing: ConnectorPublicationReader
    activations: CapabilityActivationReader
    permissions: GroupPermissionLookup


@dataclass(frozen=True)
class CatalogueStateReads:
    publications: tuple[ManyRead[PublicationStateRecord], ...]
    activations: tuple[ManyRead[CapabilityActivationStateRecord], ...]
    connector_permissions: tuple[ManyRead[GroupConnectorPermissionRecord], ...]
    capability_permissions: tuple[ManyRead[GroupCapabilityPermissionRecord], ...]

    def resolve(self, results: ReadResults) -> CatalogueReadState:
        return CatalogueReadState(
            publishing=PublicationReadState(tuple(
                row for handle in self.publications for row in results.get(handle)
            )),
            activations=ActivationReadState(tuple(
                row for handle in self.activations for row in results.get(handle)
            )),
            permissions=PermissionReadState(
                tuple(row for handle in self.connector_permissions for row in results.get(handle)),
                tuple(row for handle in self.capability_permissions for row in results.get(handle)),
            ),
        )


def plan_catalogue_state(
    plan: ReadPlanOperations, connector_ids: tuple[str, ...], group_ids: tuple[str, ...]
) -> CatalogueStateReads:
    return CatalogueStateReads(
        publications=plan_publication_reads(plan, connector_ids),
        activations=plan_activation_reads(plan, connector_ids),
        connector_permissions=plan_connector_permission_reads(plan, group_ids),
        capability_permissions=plan_capability_permission_reads(plan, group_ids),
    )
