from umbod.core.activation import ActivationStore, CapabilityRef
from umbod.core.administrator.connector_configuration import (
    CapabilityPermissionState,
    CapabilityState,
    ConfigurationResult,
    ConfigurationSucceeded,
    ConnectorConfigurableState,
    ConnectorReference,
    GroupPermissionState,
    InvocationPolicyState,
    OverriddenDescriptionState,
    ReadConnectorConfiguration,
    SystemDescriptionState,
)
from umbod.core.capabilities.descriptions.overrides import (
    ConnectorCapabilityDescriptionKey,
    ConnectorCapabilityDescriptionOverrideStore,
    OverriddenCapabilityDescription,
)
from umbod.core.connectors.openapi.stores import OpenApiConnectorStore
from umbod.core.invocation import ConnectorInvocationPolicyKey, ConnectorInvocationPolicyStore
from umbod.core.permissions import GroupPermissionReader


class OpenApiAdministratorConnectorConfigurationReader:
    def __init__(
        self,
        store: OpenApiConnectorStore,
        activation_store: ActivationStore,
        policy_store: ConnectorInvocationPolicyStore,
        description_store: ConnectorCapabilityDescriptionOverrideStore,
        permission_reader: GroupPermissionReader,
    ) -> None:
        self._store = store
        self._activation_store = activation_store
        self._policy_store = policy_store
        self._description_store = description_store
        self._permission_reader = permission_reader

    async def read(self, request: ReadConnectorConfiguration) -> ConfigurationResult:
        connector_id = request.connector.connector_id
        connector = await self._store.get_connector(connector_id)
        operation_summaries = await self._store.list_operation_summaries(connector_id)
        capabilities: list[CapabilityState] = []
        for operation in operation_summaries:
            activation_status = await self._activation_store.get_status(
                CapabilityRef("openapi", connector_id, "tool", operation.operation_id)
            )
            policy = await self._policy_store.get(
                ConnectorInvocationPolicyKey("openapi", connector_id, operation.operation_id)
            )
            capabilities.append(
                CapabilityState(
                    capability_kind="tool",
                    capability_key=operation.operation_id,
                    activation_status=activation_status.value,
                    invocation_policy=InvocationPolicyState(
                        mode=policy.mode if policy is not None else "direct",
                        revision=policy.revision if policy is not None else 0,
                    ),
                )
            )
        override = await self._description_store.get(
            ConnectorCapabilityDescriptionKey(kind="openapi", connector_id=connector_id)
        )
        permissions: list[GroupPermissionState] = []
        for group in await self._permission_reader.list_all_group_permissions():
            granted = {
                (capability.capability_kind, capability.capability_key)
                for capability in group.capabilities
                if capability.connector_id == connector_id
            }
            permissions.append(
                GroupPermissionState(
                    group_id=group.group_id,
                    connector_status="enabled"
                    if connector_id in group.connector_ids
                    else "disabled",
                    capabilities=tuple(
                        CapabilityPermissionState(
                            capability_kind=capability.capability_kind,
                            capability_key=capability.capability_key,
                            status="enabled"
                            if (capability.capability_kind, capability.capability_key) in granted
                            else "disabled",
                        )
                        for capability in capabilities
                    ),
                )
            )
        description = (
            OverriddenDescriptionState(
                state="overridden",
                revision=override.revision,
                description=override.description,
            )
            if isinstance(override, OverriddenCapabilityDescription)
            else SystemDescriptionState(state="system", revision=override.revision)
        )
        return ConfigurationSucceeded(
            state=ConnectorConfigurableState(
                connector=ConnectorReference(
                    connector_kind="openapi",
                    connector_id=connector.connector_id,
                ),
                capabilities=tuple(capabilities),
                capability_description=description,
                group_permissions=tuple(permissions),
            )
        )
