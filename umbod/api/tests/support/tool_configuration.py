from umbod.core.activation import ActivationStatus
from umbod.core.invocation.policy import (
    ConnectorInvocationPolicyConflict,
    ConnectorInvocationPolicyKey,
    ConnectorInvocationPolicyRevisionConflict,
    ConnectorKind,
)
from umbod.core.invocation.tools.configuration_mutation import (
    ConnectorToolConfigurationMutation,
    ConnectorToolConfigurationMutationResult,
    ConnectorToolConfigurationSnapshot,
    ConnectorToolInvocationPolicyChange,
    ConnectorToolInvocationPolicyMutationResult,
)


class InMemoryConnectorToolConfigurationMutationAdapter:
    def __init__(self) -> None:
        self._activations: dict[tuple[str, str], ActivationStatus] = {}
        self._policies: dict[
            tuple[ConnectorKind, str, str], ConnectorToolInvocationPolicyMutationResult
        ] = {}

    def _policy_result(
        self,
        mutation: ConnectorToolConfigurationMutation,
        change: ConnectorToolInvocationPolicyChange,
    ) -> ConnectorToolInvocationPolicyMutationResult:
        key = (mutation.connector_kind, mutation.connector_id, change.operation_name)
        current = self._policies.get(key)
        current_revision = current.revision if current is not None else 0
        if change.expected_revision != current_revision:
            raise ConnectorInvocationPolicyRevisionConflict(
                (
                    ConnectorInvocationPolicyConflict(
                        key=ConnectorInvocationPolicyKey(
                            connector_kind=mutation.connector_kind,
                            connector_id=mutation.connector_id,
                            operation_name=change.operation_name,
                        ),
                        expected_revision=change.expected_revision,
                        current_mode=current.mode if current is not None else "direct",
                        current_revision=current_revision,
                    ),
                )
            )
        changed = (
            current is None
            and change.mode != "direct"
            or current is not None
            and current.mode != change.mode
        )
        return ConnectorToolInvocationPolicyMutationResult(
            operation_name=change.operation_name,
            mode=change.mode if changed else (current.mode if current is not None else "direct"),
            revision=change.expected_revision + 1 if changed else change.expected_revision,
            changed=changed,
        )

    async def apply(
        self, mutation: ConnectorToolConfigurationMutation
    ) -> ConnectorToolConfigurationMutationResult:
        policy_items: list[ConnectorToolInvocationPolicyMutationResult] = []
        conflicts: list[ConnectorInvocationPolicyConflict] = []
        for change in mutation.policy_changes:
            try:
                policy_items.append(self._policy_result(mutation, change))
            except ConnectorInvocationPolicyRevisionConflict as error:
                conflicts.extend(error.conflicts)
        if conflicts:
            raise ConnectorInvocationPolicyRevisionConflict(tuple(conflicts))
        policy_results = tuple(policy_items)
        for change, result in zip(mutation.policy_changes, policy_results, strict=True):
            if result.changed:
                self._policies[
                    (mutation.connector_kind, mutation.connector_id, change.operation_name)
                ] = result
        changed_activations = tuple(
            change
            for change in mutation.activation_changes
            if self._activations.get(
                (mutation.connector_id, change.operation_name),
                ActivationStatus.DISABLED,
            )
            != change.status
        )
        for change in mutation.activation_changes:
            self._activations[(mutation.connector_id, change.operation_name)] = change.status
        policy_by_name = {item.operation_name: item for item in policy_results}
        snapshots = tuple(
            ConnectorToolConfigurationSnapshot(
                operation_name=operation_name,
                activation_status=self._activations.get(
                    (mutation.connector_id, operation_name),
                    ActivationStatus.DISABLED,
                ),
                invocation_mode=policy_by_name.get(
                    operation_name,
                    self._policies.get(
                        (mutation.connector_kind, mutation.connector_id, operation_name)
                    ),
                ).mode
                if policy_by_name.get(
                    operation_name,
                    self._policies.get(
                        (mutation.connector_kind, mutation.connector_id, operation_name)
                    ),
                )
                is not None
                else "direct",
                policy_revision=policy_by_name.get(
                    operation_name,
                    self._policies.get(
                        (mutation.connector_kind, mutation.connector_id, operation_name)
                    ),
                ).revision
                if policy_by_name.get(
                    operation_name,
                    self._policies.get(
                        (mutation.connector_kind, mutation.connector_id, operation_name)
                    ),
                )
                is not None
                else 0,
            )
            for operation_name in mutation.submitted_operation_names
        )
        return ConnectorToolConfigurationMutationResult(
            snapshots=snapshots,
            changed_activations=changed_activations,
            policies=policy_results,
        )
