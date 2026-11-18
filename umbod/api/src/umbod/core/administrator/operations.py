from uuid import UUID

from umbod.core.filesystem.namespaces import (
    CreateSharedNamespace,
    NamespaceManagement,
    SaveSharedNamespace,
    SaveSharedNamespaceDescription,
    SharedNamespaceView,
)
from umbod.core.groups.models import Group
from umbod.core.identity_directory.models import DirectoryScope
from umbod.core.permissions.domain import (
    AssignablePermissionTargets,
    GroupPermissionSet,
    PermissionChangeResult,
    UpdateGroupPermissionsRequest,
)
from umbod.core.permissions.ports import GroupPermissionLookup

from .connector_configuration import (
    AdministratorConnectorConfiguration,
    AdministratorPrincipal,
    ConfigurationResult,
    ConnectorDesiredState,
    ConnectorReference,
    ReadConnectorConfiguration,
    UpsertConnectorConfiguration,
)
from .models import (
    ConnectorInventoryEntry,
    ObservedUserMatches,
    ObservedUserSummary,
    PatchGroupPermissions,
    SearchObservedUsers,
)
from .ports import (
    AssignableTargetReader,
    ConnectorInventory,
    GroupPermissionPatcher,
    ObservedUserSearch,
    RegisteredGroupReader,
)


class AdministratorAccessDenied(PermissionError):
    pass


class AdministratorAccess:
    def __init__(self, required_membership: str) -> None:
        if not required_membership.strip():
            raise ValueError("Administrator membership must not be blank")
        self._required_membership = required_membership

    def require(self, principal: AdministratorPrincipal) -> None:
        if self._required_membership not in principal.memberships:
            raise AdministratorAccessDenied()


class AdministratorDiscovery:
    def __init__(
        self,
        access: AdministratorAccess,
        connectors: ConnectorInventory,
        groups: RegisteredGroupReader,
        permission_targets: AssignableTargetReader,
        users: ObservedUserSearch,
        namespaces: NamespaceManagement,
        *,
        issuer: str,
        permission_group_claim: str,
    ) -> None:
        self._access = access
        self._connectors = connectors
        self._groups = groups
        self._permission_targets = permission_targets
        self._users = users
        self._namespaces = namespaces
        self._issuer = issuer
        self._permission_group_claim = permission_group_claim

    async def list_connectors(
        self, principal: AdministratorPrincipal
    ) -> tuple[ConnectorInventoryEntry, ...]:
        self._access.require(principal)
        return await self._connectors.list_connectors()

    async def list_groups(self, principal: AdministratorPrincipal) -> tuple[Group, ...]:
        self._access.require(principal)
        return await self._groups.list_groups()

    async def list_permission_targets(
        self, principal: AdministratorPrincipal
    ) -> AssignablePermissionTargets:
        self._access.require(principal)
        return await self._permission_targets.list_assignable_targets()

    async def search_users(
        self, principal: AdministratorPrincipal, query: SearchObservedUsers
    ) -> ObservedUserMatches:
        self._access.require(principal)
        if not self._issuer.strip():
            return ObservedUserMatches(users=(), has_more=False)
        page = await self._users.search_users(
            DirectoryScope(
                issuer=self._issuer,
                claim=self._permission_group_claim,
                query=query.query,
                limit=query.limit,
                user_search_fields="profile",
            )
        )
        return ObservedUserMatches(
            users=tuple(
                ObservedUserSummary(
                    user_id=user.user_id,
                    name=user.name,
                    email=user.email,
                    last_seen_at=user.last_seen_at,
                )
                for user in page.users
            ),
            has_more=page.has_more,
        )

    async def list_namespaces(
        self, principal: AdministratorPrincipal
    ) -> list[SharedNamespaceView]:
        self._access.require(principal)
        return await self._namespaces.list()


class AdministratorInspection:
    def __init__(
        self,
        access: AdministratorAccess,
        connectors: AdministratorConnectorConfiguration,
        permissions: GroupPermissionLookup,
    ) -> None:
        self._access = access
        self._connectors = connectors
        self._permissions = permissions

    async def read_connector_configuration(
        self, principal: AdministratorPrincipal, connector: ConnectorReference
    ) -> ConfigurationResult:
        self._access.require(principal)
        return await self._connectors.read(
            ReadConnectorConfiguration(principal=principal, connector=connector)
        )

    async def read_group_permissions(
        self, principal: AdministratorPrincipal, group_id: str
    ) -> GroupPermissionSet:
        self._access.require(principal)
        return await self._permissions.list_group_permissions(group_id)


class AdministratorChanges:
    def __init__(
        self,
        access: AdministratorAccess,
        connectors: AdministratorConnectorConfiguration,
        permissions: GroupPermissionPatcher,
        namespaces: NamespaceManagement,
    ) -> None:
        self._access = access
        self._connectors = connectors
        self._permissions = permissions
        self._namespaces = namespaces

    async def update_connector_configuration(
        self,
        principal: AdministratorPrincipal,
        connector: ConnectorReference,
        desired_state: ConnectorDesiredState,
    ) -> ConfigurationResult:
        self._access.require(principal)
        return await self._connectors.upsert(
            UpsertConnectorConfiguration(
                principal=principal, connector=connector, desired_state=desired_state
            )
        )

    async def update_group_permissions(
        self, principal: AdministratorPrincipal, patch: PatchGroupPermissions
    ) -> PermissionChangeResult:
        self._access.require(principal)
        return await self._permissions.update_group_permissions(
            UpdateGroupPermissionsRequest(
                group_id=patch.group_id,
                connectors=patch.connectors,
                capabilities=patch.capabilities,
            )
        )

    async def create_namespace(
        self, principal: AdministratorPrincipal, command: CreateSharedNamespace
    ) -> SharedNamespaceView:
        self._access.require(principal)
        return await self._namespaces.create(command)

    async def update_namespace(
        self,
        principal: AdministratorPrincipal,
        namespace_id: UUID,
        command: SaveSharedNamespace | SaveSharedNamespaceDescription,
    ) -> SharedNamespaceView:
        self._access.require(principal)
        return await self._namespaces.save(namespace_id, command)
