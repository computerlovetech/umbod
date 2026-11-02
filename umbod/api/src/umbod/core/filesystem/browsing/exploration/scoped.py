from typing import Optional

from umbod.core.callers import CallerSnapshot

from ...authorization import FilesystemIdentityResolver, PermissionDenied, ResolvedIdentity, UnresolvedIdentity
from ...authorization.discovery import effective_permissions
from ...models import NodeId, NodeKind, Permission
from ...namespace import ROOT_ID
from ..ancestry import discoverable_breadcrumbs
from ..models import Breadcrumbs, NodeSummary
from ..service import discover_denied, summary
from .models import BrowseResult, BrowseScope, NodeCapabilities, NodeTarget
from .ports import BrowseScopeReader
from .service import BrowsingExplorer


class ScopedBrowsing:
    def __init__(self, scope: BrowseScope, identity: ResolvedIdentity) -> None:
        self.nodes = {node.id: summary(node) for node in scope.nodes}
        owners = {owner.node_id: (owner,) for owner in scope.ownerships}
        grants = {}
        for grant in scope.grants:
            grants.setdefault(grant.node_id, []).append(grant)
        self.permissions = {
            node_id: effective_permissions(identity.principals, node_id, owners.get(node_id, ()),
                                            grants.get(node_id, ()))
            for node_id in self.nodes
        }

    async def _discover(self, node_id: NodeId) -> Optional[NodeSummary]:
        if Permission.DISCOVER not in self.permissions.get(node_id, ()):
            return None
        return self.nodes.get(node_id)

    async def get_node(self, caller: CallerSnapshot, node_id: NodeId) -> NodeSummary:
        node = await self._discover(node_id)
        if node is None:
            raise discover_denied(node_id)
        return node

    async def get_root(self, caller: CallerSnapshot) -> NodeSummary:
        return await self.get_node(caller, ROOT_ID)

    async def get_breadcrumbs(self, caller: CallerSnapshot, node_id: NodeId) -> Breadcrumbs:
        return await discoverable_breadcrumbs(node_id, self._discover)

    async def list_children(self, caller: CallerSnapshot, parent_id: NodeId) -> list[NodeSummary]:
        await self.get_node(caller, parent_id)
        return [
            node for node in self.nodes.values()
            if node.parent_id == parent_id and Permission.DISCOVER in self.permissions[node.id]
        ]


class ScopedBrowsingExplorer:
    def __init__(
        self, reader: BrowseScopeReader, resolver: FilesystemIdentityResolver, sharing_available: bool,
    ) -> None:
        self._reader = reader
        self._resolver = resolver
        self._sharing_available = sharing_available

    async def browse_node(self, caller: CallerSnapshot, node_id: NodeId) -> BrowseResult:
        identity = await self._resolver.resolve(caller)
        if isinstance(identity, UnresolvedIdentity):
            raise PermissionDenied()
        scope = await self._reader.read_scope(node_id, identity)
        browsing = ScopedBrowsing(scope, identity)
        return await BrowsingExplorer(browsing).browse_node(
            caller, NodeTarget(type="node", node_id=node_id),
            lambda node: self._capabilities(browsing, node),
        )

    def _capabilities(self, browsing: ScopedBrowsing, node: NodeSummary) -> NodeCapabilities:
        permissions = browsing.permissions[node.id]
        editable = Permission.DISCOVER in permissions and Permission.WRITE in permissions
        parent_permissions = browsing.permissions.get(node.parent_id, frozenset())
        parent = browsing.nodes.get(node.parent_id)
        movable = editable and node.id != ROOT_ID and parent is not None and parent.kind == NodeKind.DIRECTORY and {
            Permission.DISCOVER, Permission.WRITE,
        }.issubset(parent_permissions)
        directory = node.kind == NodeKind.DIRECTORY
        return NodeCapabilities(
            node_id=node.id, rename=editable and node.id != ROOT_ID, move=movable,
            edit_description=editable, delete=not directory and Permission.DELETE in permissions,
            share=self._sharing_available and Permission.SHARE in permissions,
            upload=directory and editable, create_directory=directory and editable,
        )
