from typing import Literal, Protocol

from messaging.events import McpGroupPermissionChanged
from umbod.core.activation.events import connector_capability_activation_changed_event
from umbod.core.capabilities.descriptions.events import (
    connector_capability_description_override_changed_event,
)
from umbod.core.invocation.events import connector_invocation_policy_changed_event
from umbod.core.messaging.stores.event_stream import append_event_in_session

from umbod.core.activation import (
    ActivationStatus,
    CapabilityActivationState,
    CapabilityRef,
)
from umbod.core.activation.stores.service import (
    get_status_in_session,
    set_statuses_in_session,
)
from umbod.core.administrator.connector_configuration import (
    ConfigurationConflict,
    ConfigurationError,
    ConfigurationRejected,
    ConfigurationResult,
    ReadConnectorConfiguration,
    SetCapabilityActivation,
    SetCapabilityDescription,
    SetCapabilityInvocationPolicy,
    UpdateGroupPermissions,
    UpsertConnectorConfiguration,
    UseSystemCapabilityDescription,
)
from umbod.core.capabilities.descriptions.overrides import (
    CapabilityDescriptionOverrideState,
    ConnectorCapabilityDescriptionKey,
    OverriddenCapabilityDescription,
    OverrideRevisionConflictError,
    SystemCapabilityDescription,
)
from umbod.core.administrator.connector_configuration.catalog import (
    ConnectorConfigurationCatalog,
)
from umbod.core.capabilities import CapabilityKind
from umbod.core.invocation import (
    ConnectorInvocationPolicyKey,
    ConnectorInvocationPolicyRevisionConflict,
    ConnectorInvocationPolicyUpdate,
    compare_and_set_invocation_policies,
)
from umbod.core.permissions.domain import (
    CapabilityPermissionUpdate,
    ConnectorCapabilityRef,
    ConnectorPermissionUpdate,
    GroupPermissionSet,
    UpdateGroupPermissionsRequest,
)
from umbod.core.persistence import Database, DatabaseSession, TransactionMode


class ConnectorConfigurationResultReader(Protocol):
    async def read(
        self, request: ReadConnectorConfiguration
    ) -> ConfigurationResult: ...


class DescriptionSessionMutation(Protocol):
    async def get_in_session(
        self, session: DatabaseSession, key: ConnectorCapabilityDescriptionKey
    ) -> CapabilityDescriptionOverrideState: ...

    async def compare_and_swap_in_session(
        self,
        session: DatabaseSession,
        key: ConnectorCapabilityDescriptionKey,
        state: str,
        description: str,
        expected_revision: int,
    ) -> int: ...


class PermissionSessionMutation(Protocol):
    async def list_group_permissions_in_session(
        self, session: DatabaseSession, group_id: str
    ) -> GroupPermissionSet: ...

    async def update_group_permissions_in_session(
        self, session: DatabaseSession, request: UpdateGroupPermissionsRequest
    ) -> None: ...


class CatalogAdministratorConfigurationMutation:
    def __init__(
        self,
        database: Database,
        store: ConnectorConfigurationCatalog,
        reader: ConnectorConfigurationResultReader,
        descriptions: DescriptionSessionMutation,
        permissions: PermissionSessionMutation,
    ) -> None:
        self._database = database
        self._store = store
        self._reader = reader
        self._descriptions = descriptions
        self._permissions = permissions

    async def upsert(
        self, request: UpsertConnectorConfiguration
    ) -> ConfigurationResult:
        duplicate = self._duplicate_target(request)
        if duplicate is not None:
            return duplicate
        operation_keys = await self._operation_keys(request)
        if isinstance(operation_keys, ConfigurationRejected):
            return operation_keys
        invalid_permission = self._invalid_permission_target(request, operation_keys)
        if invalid_permission is not None:
            return invalid_permission
        description_key = ConnectorCapabilityDescriptionKey(
            kind=request.connector.connector_kind,
            connector_id=request.connector.connector_id,
        )
        try:
            async with self._database.session(
                mode=TransactionMode.SERIALIZED_WRITE
            ) as session:
                current_description = await self._descriptions.get_in_session(
                    session, description_key
                )
                description_conflict = self._description_conflict(
                    request, current_description
                )
                if description_conflict is not None:
                    return description_conflict
                updates = self._policy_updates(request)
                records = await compare_and_set_invocation_policies(session, updates)
                for update, record in zip(updates, records, strict=True):
                    if record.revision != update.expected_revision:
                        await append_event_in_session(
                            session, connector_invocation_policy_changed_event(record)
                        )
                await self._apply_activations(session, request)
                await self._apply_description(
                    session, request, description_key, current_description
                )
                for update in self._permission_updates(request):
                    await self._apply_permissions(session, update)
        except ConnectorInvocationPolicyRevisionConflict as error:
            conflicts = tuple(
                ConfigurationConflict(
                    target=f"tool/{conflict.key.operation_name}/invocation_policy",
                    expected_revision=conflict.expected_revision,
                    current_revision=conflict.current_revision,
                )
                for conflict in error.conflicts
            )
            return self._revision_rejection("Invocation policy", conflicts)
        except OverrideRevisionConflictError:
            return ConfigurationRejected(
                error=ConfigurationError(
                    code="revision_conflict",
                    message="Capability description changed concurrently",
                )
            )
        return await self._reader.read(
            ReadConnectorConfiguration(
                principal=request.principal, connector=request.connector
            )
        )

    @staticmethod
    def _duplicate_target(
        request: UpsertConnectorConfiguration,
    ) -> ConfigurationRejected | None:
        activations = [
            (operation.capability_kind, operation.capability_key)
            for operation in request.desired_state.operations
            if isinstance(operation, SetCapabilityActivation)
        ]
        policies = [
            (operation.capability_kind, operation.capability_key)
            for operation in request.desired_state.operations
            if isinstance(operation, SetCapabilityInvocationPolicy)
        ]
        descriptions = [
            operation
            for operation in request.desired_state.operations
            if isinstance(
                operation, (SetCapabilityDescription, UseSystemCapabilityDescription)
            )
        ]
        groups = [
            operation
            for operation in request.desired_state.operations
            if isinstance(operation, UpdateGroupPermissions)
        ]
        group_ids = [group.group_id for group in groups]
        permission_targets = [
            (group.group_id, capability.capability_kind, capability.capability_key)
            for group in groups
            for capability in group.capabilities
        ]
        unique = (
            len(activations) == len(set(activations))
            and len(policies) == len(set(policies))
            and len(descriptions) <= 1
            and len(group_ids) == len(set(group_ids))
            and len(permission_targets) == len(set(permission_targets))
        )
        if unique:
            return None
        return ConfigurationRejected(
            error=ConfigurationError(
                code="duplicate_target",
                message="Desired state contains duplicate configuration targets",
            )
        )

    async def _operation_keys(
        self, request: UpsertConnectorConfiguration
    ) -> set[tuple[CapabilityKind, str]] | ConfigurationRejected:
        connector_id = request.connector.connector_id
        if not await self._store.has_connector(request.connector):
            return ConfigurationRejected(
                error=ConfigurationError(
                    code="connector_not_found",
                    message=f"Connector '{connector_id}' was not found.",
                )
            )
        operation_keys = {
            (identity.capability_kind, identity.capability_key)
            for identity in await self._store.list_capabilities(request.connector)
        }
        for desired in request.desired_state.operations:
            if not isinstance(
                desired, (SetCapabilityActivation, SetCapabilityInvocationPolicy)
            ):
                continue
            if (
                desired.capability_kind,
                desired.capability_key,
            ) not in operation_keys or (
                isinstance(desired, SetCapabilityInvocationPolicy)
                and desired.capability_kind != "tool"
            ):
                return self._capability_not_found(
                    connector_id, desired.capability_kind, desired.capability_key
                )
        return operation_keys

    def _invalid_permission_target(
        self,
        request: UpsertConnectorConfiguration,
        operation_keys: set[tuple[CapabilityKind, str]],
    ) -> ConfigurationRejected | None:
        for group in request.desired_state.operations:
            if not isinstance(group, UpdateGroupPermissions):
                continue
            for capability in group.capabilities:
                if (
                    capability.capability_kind,
                    capability.capability_key,
                ) in operation_keys:
                    continue
                return self._capability_not_found(
                    request.connector.connector_id,
                    capability.capability_kind,
                    capability.capability_key,
                )
        return None

    @staticmethod
    def _capability_not_found(
        connector_id: str, capability_kind: str, capability_key: str
    ) -> ConfigurationRejected:
        return ConfigurationRejected(
            error=ConfigurationError(
                code="capability_not_found",
                message=f"Capability '{capability_kind}/{capability_key}' was not found on connector '{connector_id}'.",
            )
        )

    async def _apply_activations(
        self, session: DatabaseSession, request: UpsertConnectorConfiguration
    ) -> None:
        changed = tuple([
            state
            for state in self._activation_states(request)
            if await get_status_in_session(session, state.ref) != state.activation_status
        ])
        await set_statuses_in_session(session, changed)
        for state in changed:
            ref = state.ref
            await append_event_in_session(
                session,
                connector_capability_activation_changed_event(
                    ref.connector_kind, ref.connector_id,
                    ref.capability_kind, ref.capability_key,
                ),
            )

    async def _apply_permissions(
        self, session: DatabaseSession, update: UpdateGroupPermissionsRequest
    ) -> None:
        previous = await self._permissions.list_group_permissions_in_session(
            session, update.group_id
        )
        changed_connectors = tuple(
            connector for connector in update.connectors
            if (connector.permission_status == "enabled")
            != (connector.connector_id in previous.connector_ids)
        )
        changed_capabilities = tuple(
            capability for capability in update.capabilities
            if (capability.permission_status == "enabled")
            != (capability.capability in previous.capabilities)
        )
        if not changed_connectors and not changed_capabilities:
            return
        await self._permissions.update_group_permissions_in_session(
            session,
            UpdateGroupPermissionsRequest(
                group_id=update.group_id,
                connectors=changed_connectors,
                capabilities=changed_capabilities,
            ),
        )
        for connector in changed_connectors:
            enabled = connector.permission_status == "enabled"
            await append_event_in_session(
                session,
                McpGroupPermissionChanged(
                    group_id=update.group_id,
                    action="grant" if enabled else "revoke",
                    target_kind="connector",
                    connector_id=connector.connector_id,
                ).to_messaging_event(),
            )
        for capability_update in changed_capabilities:
            capability = capability_update.capability
            enabled = capability_update.permission_status == "enabled"
            await append_event_in_session(
                session,
                McpGroupPermissionChanged(
                    group_id=update.group_id,
                    action="grant" if enabled else "revoke",
                    target_kind=capability.capability_kind,
                    connector_id=capability.connector_id,
                    capability_kind=capability.capability_kind,
                    capability_key=capability.capability_key,
                    operation_name=(
                        capability.capability_key
                        if capability.capability_kind == "tool" else None
                    ),
                ).to_messaging_event(),
            )

    @staticmethod
    def _activation_states(
        request: UpsertConnectorConfiguration,
    ) -> tuple[CapabilityActivationState, ...]:
        return tuple(
            CapabilityActivationState(
                ref=CapabilityRef(
                    request.connector.connector_kind,
                    request.connector.connector_id,
                    desired.capability_kind,
                    desired.capability_key,
                ),
                activation_status=ActivationStatus(desired.activation_status),
            )
            for desired in request.desired_state.operations
            if isinstance(desired, SetCapabilityActivation)
        )

    @staticmethod
    def _policy_updates(
        request: UpsertConnectorConfiguration,
    ) -> tuple[ConnectorInvocationPolicyUpdate, ...]:
        return tuple(
            ConnectorInvocationPolicyUpdate(
                key=ConnectorInvocationPolicyKey(
                    request.connector.connector_kind,
                    request.connector.connector_id,
                    desired.capability_key,
                ),
                mode=desired.mode,
                expected_revision=desired.expected_revision,
            )
            for desired in request.desired_state.operations
            if isinstance(desired, SetCapabilityInvocationPolicy)
        )

    @staticmethod
    def _description_operation(
        request: UpsertConnectorConfiguration,
    ) -> SetCapabilityDescription | UseSystemCapabilityDescription | None:
        return next(
            (
                operation
                for operation in request.desired_state.operations
                if isinstance(
                    operation,
                    (SetCapabilityDescription, UseSystemCapabilityDescription),
                )
            ),
            None,
        )

    def _description_conflict(
        self,
        request: UpsertConnectorConfiguration,
        current: CapabilityDescriptionOverrideState,
    ) -> ConfigurationRejected | None:
        desired = self._description_operation(request)
        if desired is None or desired.expected_revision == current.revision:
            return None
        conflict = ConfigurationConflict(
            target="capability_description",
            expected_revision=desired.expected_revision,
            current_revision=current.revision,
        )
        return self._revision_rejection("Capability description", (conflict,))

    @staticmethod
    def _revision_rejection(
        label: str, conflicts: tuple[ConfigurationConflict, ...]
    ) -> ConfigurationRejected:
        details = ", ".join(
            f"{conflict.target}: expected revision {conflict.expected_revision}, current revision {conflict.current_revision}"
            for conflict in conflicts
        )
        return ConfigurationRejected(
            error=ConfigurationError(
                code="revision_conflict",
                message=f"{label} revision conflict: {details}",
            ),
            conflicts=conflicts,
        )

    async def _apply_description(
        self,
        session: DatabaseSession,
        request: UpsertConnectorConfiguration,
        key: ConnectorCapabilityDescriptionKey,
        current: CapabilityDescriptionOverrideState,
    ) -> None:
        desired = self._description_operation(request)
        if desired is None:
            return
        already_satisfied = (
            isinstance(desired, SetCapabilityDescription)
            and isinstance(current, OverriddenCapabilityDescription)
            and current.description == desired.description
        ) or (
            isinstance(desired, UseSystemCapabilityDescription)
            and isinstance(current, SystemCapabilityDescription)
        )
        if already_satisfied:
            return
        state: Literal["overridden", "system"] = (
            "overridden" if isinstance(desired, SetCapabilityDescription) else "system"
        )
        description = (
            desired.description if isinstance(desired, SetCapabilityDescription) else ""
        )
        revision = await self._descriptions.compare_and_swap_in_session(
            session, key, state, description, desired.expected_revision
        )
        await append_event_in_session(
            session,
            connector_capability_description_override_changed_event(
                key.kind, key.connector_id,
                "set" if state == "overridden" else "clear", revision,
            ),
        )

    def _permission_updates(
        self, request: UpsertConnectorConfiguration
    ) -> tuple[UpdateGroupPermissionsRequest, ...]:
        connector_id = request.connector.connector_id
        return tuple(
            UpdateGroupPermissionsRequest(
                group_id=group.group_id,
                connectors=(
                    ConnectorPermissionUpdate(connector_id, group.connector_status),
                )
                if group.connector_status is not None
                else (),
                capabilities=tuple(
                    CapabilityPermissionUpdate(
                        ConnectorCapabilityRef(
                            connector_id,
                            capability.capability_kind,
                            capability.capability_key,
                        ),
                        capability.status,
                    )
                    for capability in group.capabilities
                ),
            )
            for group in request.desired_state.operations
            if isinstance(group, UpdateGroupPermissions)
        )
