from typing import Protocol, Union

from messaging.ports import EventStream
from pydantic import BaseModel, ConfigDict, Field

from umbod.core.invocation.events import connector_invocation_policy_changed_event
from umbod.core.activation.events import connector_tool_activation_changed_event
from umbod.core.invocation.policy import (
    ConnectorInvocationPolicyKey,
    ConnectorInvocationPolicyRecord,
    ConnectorKind,
    InvocationPolicyMode,
)
from umbod.core.invocation.tools.configuration_mutation import (
    ConnectorToolActivationChange,
    ConnectorToolConfigurationMutation,
    ConnectorToolConfigurationMutationPort,
    ConnectorToolConfigurationMutationResult,
    ConnectorToolInvocationPolicyChange,
)
from umbod.core.activation import ActivationStatus


class ActivationEventPublicationPolicy(Protocol):
    async def should_publish(self, connector_kind: ConnectorKind, connector_id: str) -> bool: ...


class AlwaysPublishActivationEvents:
    async def should_publish(self, connector_kind: ConnectorKind, connector_id: str) -> bool:
        return True


class SuppressActivationEvents:
    async def should_publish(self, connector_kind: ConnectorKind, connector_id: str) -> bool:
        return False


class SetConnectorToolActivation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    operation_name: str = Field(min_length=1)
    activation_status: ActivationStatus


class SetConnectorToolInvocationPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    operation_name: str = Field(min_length=1)
    invocation_mode: InvocationPolicyMode
    expected_policy_revision: int = Field(ge=0)


class SetConnectorToolActivationAndInvocationPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    operation_name: str = Field(min_length=1)
    activation_status: ActivationStatus
    invocation_mode: InvocationPolicyMode
    expected_policy_revision: int = Field(ge=0)


SetConnectorToolConfigurationItem = Union[
    SetConnectorToolActivation,
    SetConnectorToolInvocationPolicy,
    SetConnectorToolActivationAndInvocationPolicy,
]


class SetConnectorToolConfigurationCommand(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    connector_kind: ConnectorKind
    connector_id: str = Field(min_length=1)
    items: tuple[SetConnectorToolConfigurationItem, ...] = Field(min_length=1)


class NoConnectorToolConfigurationEventStream:
    pass


def _activation_changes(
    items: tuple[SetConnectorToolConfigurationItem, ...],
) -> tuple[ConnectorToolActivationChange, ...]:
    activation_items = (
        item
        for item in items
        if isinstance(
            item, (SetConnectorToolActivation, SetConnectorToolActivationAndInvocationPolicy)
        )
    )
    return tuple(
        ConnectorToolActivationChange(
            operation_name=item.operation_name,
            status=item.activation_status,
        )
        for item in activation_items
    )


def _policy_changes(
    items: tuple[SetConnectorToolConfigurationItem, ...],
) -> tuple[ConnectorToolInvocationPolicyChange, ...]:
    policy_items = (
        item
        for item in items
        if isinstance(
            item,
            (SetConnectorToolInvocationPolicy, SetConnectorToolActivationAndInvocationPolicy),
        )
    )
    return tuple(
        ConnectorToolInvocationPolicyChange(
            operation_name=item.operation_name,
            mode=item.invocation_mode,
            expected_revision=item.expected_policy_revision,
        )
        for item in policy_items
    )


class SetConnectorToolConfiguration:
    def __init__(
        self,
        mutation_port: ConnectorToolConfigurationMutationPort,
        event_stream: EventStream | NoConnectorToolConfigurationEventStream,
        activation_event_publication: ActivationEventPublicationPolicy,
    ) -> None:
        self._mutation_port = mutation_port
        self._event_stream = event_stream
        self._activation_event_publication = activation_event_publication

    async def execute(
        self, command: SetConnectorToolConfigurationCommand
    ) -> ConnectorToolConfigurationMutationResult:
        result = await self._mutation_port.apply(self._mutation(command))
        if isinstance(self._event_stream, NoConnectorToolConfigurationEventStream):
            return result
        await self._publish_activation_events(command, result)
        await self._publish_policy_events(command, result)
        return result

    async def _publish_activation_events(
        self,
        command: SetConnectorToolConfigurationCommand,
        result: ConnectorToolConfigurationMutationResult,
    ) -> None:
        if not await self._activation_event_publication.should_publish(
            command.connector_kind, command.connector_id
        ):
            return
        for changed in result.changed_activations:
            await self._event_stream.append(
                connector_tool_activation_changed_event(
                    command.connector_id,
                    changed.operation_name,
                    connector_kind=command.connector_kind,
                )
            )

    async def _publish_policy_events(
        self,
        command: SetConnectorToolConfigurationCommand,
        result: ConnectorToolConfigurationMutationResult,
    ) -> None:
        for policy in result.policies:
            if policy.changed:
                record = ConnectorInvocationPolicyRecord(
                    key=ConnectorInvocationPolicyKey(
                        connector_kind=command.connector_kind,
                        connector_id=command.connector_id,
                        operation_name=policy.operation_name,
                    ),
                    mode=policy.mode,
                    revision=policy.revision,
                )
                await self._event_stream.append(connector_invocation_policy_changed_event(record))

    def _mutation(
        self, command: SetConnectorToolConfigurationCommand
    ) -> ConnectorToolConfigurationMutation:
        return ConnectorToolConfigurationMutation(
            connector_kind=command.connector_kind,
            connector_id=command.connector_id,
            operation_names=tuple(dict.fromkeys(item.operation_name for item in command.items)),
            activation_changes=_activation_changes(command.items),
            policy_changes=_policy_changes(command.items),
        )


__all__ = [
    "ActivationEventPublicationPolicy",
    "AlwaysPublishActivationEvents",
    "NoConnectorToolConfigurationEventStream",
    "SetConnectorToolActivation",
    "SetConnectorToolActivationAndInvocationPolicy",
    "SetConnectorToolConfiguration",
    "SetConnectorToolConfigurationCommand",
    "SetConnectorToolConfigurationItem",
    "SetConnectorToolInvocationPolicy",
    "SuppressActivationEvents",
]
