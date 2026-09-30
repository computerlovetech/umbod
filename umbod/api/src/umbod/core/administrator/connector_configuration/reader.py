from umbod.core.activation import ActivationStore, CapabilityRef
from umbod.core.administrator.connector_configuration import (
    CapabilityPermissionState,
    CapabilityState,
    ConfigurationResult,
    ConfigurationSucceeded,
    ConnectorConfigurableState,
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
from umbod.core.administrator.connector_configuration.catalog import (
    ConnectorConfigurationCatalog,
)
from umbod.core.administrator.connector_configuration import (
    ConfigurationRejected,
    ConfigurationError,
)
from umbod.core.invocation import (
    ConnectorInvocationPolicyKey,
    ConnectorInvocationPolicyStore,
)
from umbod.core.permissions import GroupPermissionReader


class CatalogAdministratorConnectorConfigurationReader:
    def __init__(
        self,
        store: ConnectorConfigurationCatalog,
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
        if not await self._store.has_connector(request.connector):
            return ConfigurationRejected(
                error=ConfigurationError(
                    code="connector_not_found",
                    message=f"Connector '{connector_id}' was not found.",
                )
            )
        identities = await self._store.list_capabilities(request.connector)
        capabilities: list[CapabilityState] = []
        for identity in identities:
            activation_status = await self._activation_store.get_status(
                CapabilityRef(
                    identity.connector_kind,
                    connector_id,
                    identity.capability_kind,
                    identity.capability_key,
                )
            )
            policy = (
                await self._policy_store.get(
                    ConnectorInvocationPolicyKey(
                        identity.connector_kind, connector_id, identity.capability_key
                    )
                )
                if identity.capability_kind == "tool"
                else None
            )
            capabilities.append(
                CapabilityState(
                    capability_kind=identity.capability_kind,
                    capability_key=identity.capability_key,
                    activation_status=activation_status.value,
                    invocation_policy=InvocationPolicyState(
                        mode=policy.mode if policy is not None else "direct",
                        revision=policy.revision if policy is not None else 0,
                    )
                    if identity.capability_kind == "tool"
                    else None,
                )
            )
        override = await self._description_store.get(
            ConnectorCapabilityDescriptionKey(
                kind=request.connector.connector_kind, connector_id=connector_id
            )
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
                            if (capability.capability_kind, capability.capability_key)
                            in granted
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
                connector=request.connector,
                capabilities=tuple(capabilities),
                capability_description=description,
                group_permissions=tuple(permissions),
            )
        )
