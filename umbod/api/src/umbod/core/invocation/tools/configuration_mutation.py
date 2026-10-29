from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from umbod.core.invocation.policy import (
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
    publish_activation_events: bool = True

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

    events_persisted: bool = False
    snapshots: tuple[ConnectorToolConfigurationSnapshot, ...]
    changed_activations: tuple[ConnectorToolActivationChange, ...]
    policies: tuple[ConnectorToolInvocationPolicyMutationResult, ...]


class ConnectorToolConfigurationMutationPort(Protocol):
    async def apply(
        self, mutation: ConnectorToolConfigurationMutation
    ) -> ConnectorToolConfigurationMutationResult: ...


__all__ = [
    "ConnectorToolActivationChange",
    "ConnectorToolConfigurationMutation",
    "ConnectorToolConfigurationMutationPort",
    "ConnectorToolConfigurationMutationResult",
    "ConnectorToolConfigurationSnapshot",
    "ConnectorToolInvocationPolicyChange",
    "ConnectorToolInvocationPolicyMutationResult",
]
