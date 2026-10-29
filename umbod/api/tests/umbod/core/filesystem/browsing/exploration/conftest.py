from collections.abc import Sequence
from uuid import UUID

import pytest

from tests.support.filesystem.authorization import caller
from umbod.core.callers import CallerSnapshot
from umbod.core.filesystem import NodeKind
from umbod.core.filesystem.authorization import PermissionDenied
from umbod.core.filesystem.browsing import BreadcrumbItem, Breadcrumbs, NodeSummary, summary
from umbod.core.filesystem.namespace import initial_root


class InMemoryBrowsing:
    def __init__(self) -> None:
        self.root = summary(initial_root())
        self.nodes = {self.root.id: self.root}
        self.children: dict[UUID, list[NodeSummary]] = {self.root.id: []}
        self.hidden: set[UUID] = set()
        self.calls: list[tuple[str, UUID]] = []
        self.breadcrumbs: dict[UUID, Breadcrumbs] = {}
        self.caller = caller("alice")

    def add(self, identifier: int, name: str, kind: NodeKind, parent: NodeSummary) -> NodeSummary:
        node = self.root.model_copy(update={
            "id": UUID(int=identifier), "name": name, "kind": kind, "parent_id": parent.id,
        })
        self.nodes[node.id] = node
        self.children.setdefault(parent.id, []).append(node)
        self.children[node.id] = []
        return node

    async def get_root(self, caller: CallerSnapshot) -> NodeSummary:
        assert caller is self.caller
        self.calls.append(("root", self.root.id))
        if self.root.id in self.hidden:
            raise PermissionDenied("unavailable")
        return self.root

    async def get_node(self, caller: CallerSnapshot, node_id: UUID) -> NodeSummary:
        assert caller is self.caller
        self.calls.append(("node", node_id))
        if node_id not in self.nodes or node_id in self.hidden:
            raise PermissionDenied("unavailable")
        return self.nodes[node_id]

    async def get_breadcrumbs(self, caller: CallerSnapshot, node_id: UUID) -> Breadcrumbs:
        assert caller is self.caller
        self.calls.append(("breadcrumbs", node_id))
        if node_id in self.breadcrumbs:
            return self.breadcrumbs[node_id]
        node = self.nodes[node_id]
        return Breadcrumbs(
            items=[BreadcrumbItem(id=node.id, name=node.name, kind=node.kind)],
            complete=node.id == self.root.id,
        )

    async def list_children(self, caller: CallerSnapshot, parent_id: UUID) -> Sequence[NodeSummary]:
        assert caller is self.caller
        self.calls.append(("children", parent_id))
        return [node for node in self.children[parent_id] if node.id not in self.hidden]


@pytest.fixture
def browsing() -> InMemoryBrowsing:
    return InMemoryBrowsing()
