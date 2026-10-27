from dataclasses import dataclass

from umbod.core.activation.domain import CapabilityActivationReader
from umbod.core.activation.stores.reads import ActivationReadState, plan_activation_reads
from umbod.core.activation.stores.schema import CapabilityActivationStateRecord
from umbod.core.persistence.plan import ManyRead, ReadPlanOperations, ReadResults
from umbod.core.publishing.store import ConnectorPublicationReader
from umbod.core.publishing.stores.reads import PublicationReadState, plan_publication_reads
from umbod.core.publishing.stores.schema import PublicationStateRecord


@dataclass(frozen=True)
class AssignableReadState:
    publishing: ConnectorPublicationReader
    activations: CapabilityActivationReader

    @classmethod
    def empty(cls) -> "AssignableReadState":
        return cls(publishing=PublicationReadState(()), activations=ActivationReadState(()))


@dataclass(frozen=True)
class AssignableStateReads:
    publications: tuple[ManyRead[PublicationStateRecord], ...]
    activations: tuple[ManyRead[CapabilityActivationStateRecord], ...]

    def resolve(self, results: ReadResults) -> AssignableReadState:
        return AssignableReadState(
            publishing=PublicationReadState(tuple(
                row for handle in self.publications for row in results.get(handle)
            )),
            activations=ActivationReadState(tuple(
                row for handle in self.activations for row in results.get(handle)
            )),
        )


def plan_assignable_state(
    plan: ReadPlanOperations,
    publication_connector_ids: tuple[str, ...],
    activation_connector_ids: tuple[str, ...],
) -> AssignableStateReads:
    return AssignableStateReads(
        publications=plan_publication_reads(plan, publication_connector_ids),
        activations=plan_activation_reads(plan, activation_connector_ids),
    )
