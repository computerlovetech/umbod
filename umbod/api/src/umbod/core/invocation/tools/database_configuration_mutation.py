from umbod.core.activation import (
    CapabilityActivationState,
    CapabilityRef,
)
from umbod.core.activation.stores.service import (
    get_status_in_session,
    set_statuses_in_session,
)
from umbod.core.invocation import (
    ConnectorInvocationPolicyKey,
    ConnectorInvocationPolicyUpdate,
)
from umbod.core.invocation import (
    CONNECTOR_INVOCATION_POLICY_TABLE,
    compare_and_set_invocation_policies,
    connector_invocation_policy_query,
    connector_invocation_policy_record,
)
from umbod.core.invocation.tools.configuration_mutation import ConnectorToolActivationChange, ConnectorToolConfigurationMutation, ConnectorToolConfigurationMutationResult, ConnectorToolConfigurationSnapshot, ConnectorToolInvocationPolicyMutationResult
from umbod.core.persistence import Database, DatabaseSession, TransactionMode


def _activation_states(
    mutation: ConnectorToolConfigurationMutation,
) -> tuple[CapabilityActivationState, ...]:
    return tuple(
        CapabilityActivationState(
            ref=CapabilityRef(
                connector_kind=mutation.connector_kind,
                connector_id=mutation.connector_id,
                capability_kind="tool",
                capability_key=change.operation_name,
            ),
            activation_status=change.status,
        )
        for change in mutation.activation_changes
    )


def _policy_updates(
    mutation: ConnectorToolConfigurationMutation,
) -> tuple[ConnectorInvocationPolicyUpdate, ...]:
    return tuple(
        ConnectorInvocationPolicyUpdate(
            key=ConnectorInvocationPolicyKey(
                connector_kind=mutation.connector_kind,
                connector_id=mutation.connector_id,
                operation_name=change.operation_name,
            ),
            mode=change.mode,
            expected_revision=change.expected_revision,
        )
        for change in mutation.policy_changes
    )


async def _changed_activations(
    session: DatabaseSession,
    mutation: ConnectorToolConfigurationMutation,
    states: tuple[CapabilityActivationState, ...],
) -> tuple[ConnectorToolActivationChange, ...]:
    changed: list[ConnectorToolActivationChange] = []
    for change, state in zip(mutation.activation_changes, states, strict=True):
        if await get_status_in_session(session, state.ref) != change.status:
            changed.append(change)
    return tuple(changed)


class DatabaseConnectorToolConfigurationMutationAdapter:
    def __init__(self, database: Database) -> None:
        self._database = database

    async def apply(
        self, mutation: ConnectorToolConfigurationMutation
    ) -> ConnectorToolConfigurationMutationResult:
        activation_states = _activation_states(mutation)
        policy_updates = _policy_updates(mutation)
        async with self._database.session(mode=TransactionMode.SERIALIZED_WRITE) as session:
            records = await compare_and_set_invocation_policies(session, policy_updates)
            changed_activations = await _changed_activations(
                session, mutation, activation_states
            )
            await set_statuses_in_session(session, activation_states)
            snapshots: list[ConnectorToolConfigurationSnapshot] = []
            for operation_name in mutation.submitted_operation_names:
                ref = CapabilityRef(
                    connector_kind=mutation.connector_kind,
                    connector_id=mutation.connector_id,
                    capability_kind="tool",
                    capability_key=operation_name,
                )
                policy_key = ConnectorInvocationPolicyKey(
                    connector_kind=mutation.connector_kind,
                    connector_id=mutation.connector_id,
                    operation_name=operation_name,
                )
                policy_row = await session.find_one(
                    CONNECTOR_INVOCATION_POLICY_TABLE,
                    connector_invocation_policy_query(policy_key),
                )
                policy = (
                    connector_invocation_policy_record(policy_row)
                    if policy_row is not None
                    else None
                )
                snapshots.append(
                    ConnectorToolConfigurationSnapshot(
                        operation_name=operation_name,
                        activation_status=await get_status_in_session(session, ref),
                        invocation_mode=policy.mode if policy is not None else "direct",
                        policy_revision=policy.revision if policy is not None else 0,
                    )
                )
        policies = tuple(
            ConnectorToolInvocationPolicyMutationResult(
                operation_name=record.key.operation_name,
                mode=record.mode,
                revision=record.revision,
                changed=record.revision != change.expected_revision,
            )
            for change, record in zip(mutation.policy_changes, records, strict=True)
        )
        return ConnectorToolConfigurationMutationResult(
            snapshots=tuple(snapshots),
            changed_activations=changed_activations,
            policies=policies,
        )


__all__ = ["DatabaseConnectorToolConfigurationMutationAdapter"]
