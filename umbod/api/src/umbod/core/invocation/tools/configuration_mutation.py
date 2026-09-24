from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from umbod.core.invocation.policy import (
    ConnectorInvocationPolicyConflict,
    ConnectorInvocationPolicyKey,
    ConnectorInvocationPolicyRevisionConflict,
    ConnectorKind,
    InvocationPolicyMode,
)
from umbod.core.activation import ActivationStatus


class ConnectorToolActivationChange(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    operation_name: str
    status: ActivationStatus


class ConnectorToolInvocationPolicyChange(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    operation_name: str
    mode: InvocationPolicyMode
    expected_revision: int = Field(ge=0)


class ConnectorToolConfigurationMutation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    connector_kind: ConnectorKind
    connector_id: str
    operation_names: tuple[str, ...] = ()
    activation_changes: tuple[ConnectorToolActivationChange, ...] = ()
    policy_changes: tuple[ConnectorToolInvocationPolicyChange, ...] = ()

    @property
    def submitted_operation_names(self) -> tuple[str, ...]:
        if self.operation_names:
            return tuple(dict.fromkeys(self.operation_names))
        return tuple(
            dict.fromkeys(
                change.operation_name for change in (*self.activation_changes, *self.policy_changes)
            )
        )


class ConnectorToolInvocationPolicyMutationResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    operation_name: str
    mode: InvocationPolicyMode
    revision: int = Field(ge=0)
    changed: bool


class ConnectorToolConfigurationSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    operation_name: str
    activation_status: ActivationStatus
    invocation_mode: InvocationPolicyMode
    policy_revision: int = Field(ge=0)


class ConnectorToolConfigurationMutationResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    snapshots: tuple[ConnectorToolConfigurationSnapshot, ...]
    changed_activations: tuple[ConnectorToolActivationChange, ...]
    policies: tuple[ConnectorToolInvocationPolicyMutationResult, ...]


class ConnectorToolConfigurationMutationPort(Protocol):
    async def apply(
        self, mutation: ConnectorToolConfigurationMutation
    ) -> ConnectorToolConfigurationMutationResult: ...


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


__all__ = [
    "ConnectorToolActivationChange",
    "ConnectorToolConfigurationMutation",
    "ConnectorToolConfigurationMutationPort",
    "ConnectorToolConfigurationMutationResult",
    "ConnectorToolConfigurationSnapshot",
    "ConnectorToolInvocationPolicyChange",
    "ConnectorToolInvocationPolicyMutationResult",
    "InMemoryConnectorToolConfigurationMutationAdapter",
]
