from uuid import UUID

from umbod.core.callers import CallerSnapshot

from ..errors import PolicyUnavailable
from ..authorization import FilesystemIdentityResolver, PermissionDenied, UnresolvedIdentity
from ..models import Permission
from .models import CreateSharedNamespace, NamespaceDetails, NamespaceGroupAccess, NamespaceSummary, SaveSharedNamespace, SaveSharedNamespaceDescription, SharedNamespaceView
from .ports import NamespaceRegistry


def shared_view(details: NamespaceDetails) -> SharedNamespaceView:
    policy = details.policy
    return SharedNamespaceView(
        description=details.description, root_revision=details.root_revision,
        id=policy.id, root_node_id=policy.root_node_id, name=policy.name, revision=policy.revision,
        groups=[NamespaceGroupAccess(group_id=grant.principal.id, access="read_write" if Permission.WRITE in grant.permissions else "read") for grant in policy.grants],
    )


class NamespaceService:
    def __init__(self, registry: NamespaceRegistry, resolver: FilesystemIdentityResolver) -> None:
        self._registry = registry
        self._resolver = resolver

    async def list(self, caller: CallerSnapshot) -> list[NamespaceSummary]:
        identity = await self._resolver.resolve(caller)
        if isinstance(identity, UnresolvedIdentity):
            raise PermissionDenied()
        personal = await self._registry.provision_personal(identity.user)
        details = await self._registry.list()
        selected = [entry for entry in details if entry.policy.id == personal.id or entry.policy.kind == "shared"]
        selected.sort(key=lambda entry: (entry.policy.kind != "personal", entry.policy.name, str(entry.policy.id)))
        return [NamespaceSummary(id=entry.policy.id, root_node_id=entry.policy.root_node_id, name=entry.policy.name, kind=entry.policy.kind, description=entry.description, permissions=entry.policy.permissions(identity.principals)) for entry in selected if Permission.DISCOVER in entry.policy.permissions(identity.principals)]


class NamespaceManagementService:
    def __init__(self, registry: NamespaceRegistry, issuer: str) -> None:
        if not issuer.strip():
            raise PolicyUnavailable()
        self._registry = registry
        self._issuer = issuer

    async def list(self) -> list[SharedNamespaceView]:
        details = [entry for entry in await self._registry.list() if entry.policy.kind == "shared"]
        if any(entry.policy.issuer != self._issuer for entry in details):
            raise PolicyUnavailable()
        return [shared_view(entry) for entry in sorted(details, key=lambda entry: (entry.policy.name, str(entry.policy.id)))]

    async def create(self, command: CreateSharedNamespace) -> SharedNamespaceView:
        return await self._registry.create(command, self._issuer)

    async def save(self, namespace_id: UUID, command: SaveSharedNamespace | SaveSharedNamespaceDescription) -> SharedNamespaceView:
        return await self._registry.save(namespace_id, command, self._issuer)
