from umbod.core.callers import CallerSnapshot
from umbod.core.filesystem import AccessGrant, Node, NodeId, NodeKind, NodeMetadata, Ownership, PrincipalType
from umbod.core.filesystem.authorization import ResolvedIdentity, UnresolvedIdentity
from umbod.core.filesystem.browsing.exploration import BrowseScope
from umbod.core.filesystem.namespace import new_node
from tests.support.filesystem.authorization import principal


class MemoryScopeReader:
    def __init__(self, scope: BrowseScope) -> None:
        self.scope = scope
        self.reads = 0

    async def read_scope(self, node_id: NodeId, identity: ResolvedIdentity) -> BrowseScope:
        self.reads += 1
        return self.scope


class CountingIdentityResolver:
    def __init__(self, resolved: bool) -> None:
        self.calls = 0
        self.resolved = resolved

    async def resolve(self, snapshot: CallerSnapshot) -> ResolvedIdentity | UnresolvedIdentity:
        self.calls += 1
        if not self.resolved:
            return UnresolvedIdentity()
        return ResolvedIdentity(user=principal("alice", PrincipalType.USER, "issuer"), groups=frozenset())


def child(parent_id: NodeId, name: str, kind: NodeKind) -> Node:
    return new_node(parent_id, name, kind, NodeMetadata(content_type="text/plain", attributes={}))


def scope_for(nodes: list[Node], owned: list[Node], grants: list[AccessGrant]) -> BrowseScope:
    return BrowseScope(
        nodes=tuple(nodes),
        ownerships=tuple(Ownership(node_id=node.id, owner=principal("alice", PrincipalType.USER, "issuer")) for node in owned),
        grants=tuple(grants),
    )


