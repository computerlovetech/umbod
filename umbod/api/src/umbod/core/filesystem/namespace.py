from datetime import datetime, timezone
from typing import Literal, Self
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, model_validator

from .errors import InvalidName, MissingNode, NameCollision, RevisionConflict, WrongNodeKind
from .models import (
    ContentRef,
    EmptyContent,
    Node,
    NodeId,
    NodeKind,
    NodeMetadata,
    RootParent,
    UnspecifiedContentType,
)

ROOT_ID = UUID(int=0)


class NamespaceState(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal[1]
    nodes: dict[NodeId, Node]

    @model_validator(mode="after")
    def validate_hierarchy(self) -> Self:
        roots = [node for node in self.nodes.values() if isinstance(node.parent_id, RootParent)]
        if len(roots) != 1 or roots[0].id != ROOT_ID:
            raise ValueError("Namespace must have exactly one fixed root")
        root = roots[0]
        if root.name != "" or root.kind != NodeKind.DIRECTORY:
            raise ValueError("Invalid namespace root")
        siblings: set[tuple[NodeId, str]] = set()
        for node_id, node in self.nodes.items():
            if node_id != node.id:
                raise ValueError("Node index mismatch")
            self._validate_node(node, siblings)
        return self

    def _validate_node(self, node: Node, siblings: set[tuple[NodeId, str]]) -> None:
        if node.kind == NodeKind.DIRECTORY and not isinstance(node.content, EmptyContent):
            raise ValueError("Directory has content")
        for timestamp in (node.created_at, node.updated_at):
            if timestamp.utcoffset() != timezone.utc.utcoffset(timestamp):
                raise ValueError("Node timestamps must be UTC")
        if node.updated_at < node.created_at:
            raise ValueError("Invalid node timestamps")
        if isinstance(node.parent_id, RootParent):
            return
        if not valid_name(node.name):
            raise ValueError("Invalid node name")
        sibling = (node.parent_id, node.name)
        if sibling in siblings:
            raise ValueError("Duplicate sibling name")
        siblings.add(sibling)
        visited = {node.id}
        current = node
        while isinstance(current.parent_id, UUID):
            if current.parent_id in visited:
                raise ValueError("Namespace cycle")
            visited.add(current.parent_id)
            if current.parent_id not in self.nodes:
                raise ValueError("Missing parent")
            current = self.nodes[current.parent_id]
            if current.kind != NodeKind.DIRECTORY:
                raise ValueError("Parent is not a directory")


def valid_name(name: str) -> bool:
    try:
        name.encode("utf-8")
    except UnicodeEncodeError:
        return False
    return name not in ("", ".", "..") and not any(character in name for character in ("/", "\\", "\0"))


def initial_state() -> NamespaceState:
    timestamp = datetime.now(timezone.utc)
    root = Node(
        id=ROOT_ID,
        parent_id=RootParent(),
        name="",
        kind=NodeKind.DIRECTORY,
        metadata=NodeMetadata(content_type=UnspecifiedContentType(), attributes={}),
        content=EmptyContent(),
        created_at=timestamp,
        updated_at=timestamp,
        revision=1,
    )
    return NamespaceState(schema_version=1, nodes={ROOT_ID: root})


def get_node(state: NamespaceState, node_id: NodeId) -> Node:
    try:
        return state.nodes[node_id].model_copy(deep=True)
    except KeyError as error:
        raise MissingNode(str(node_id)) from error


def require_directory(state: NamespaceState, node_id: NodeId) -> Node:
    node = get_node(state, node_id)
    if node.kind != NodeKind.DIRECTORY:
        raise WrongNodeKind(str(node_id))
    return node


def list_children(state: NamespaceState, parent_id: NodeId) -> list[Node]:
    require_directory(state, parent_id)
    return sorted(
        (node.model_copy(deep=True) for node in state.nodes.values() if node.parent_id == parent_id),
        key=lambda node: node.name,
    )


def create_node(
    state: NamespaceState, parent_id: NodeId, name: str, kind: NodeKind, metadata: NodeMetadata,
) -> tuple[NamespaceState, Node]:
    require_directory(state, parent_id)
    if not valid_name(name):
        raise InvalidName(name)
    if any(node.parent_id == parent_id and node.name == name for node in state.nodes.values()):
        raise NameCollision(name)
    timestamp = datetime.now(timezone.utc)
    node = Node(
        id=uuid4(), parent_id=parent_id, name=name, kind=kind,
        metadata=metadata.model_copy(deep=True), content=EmptyContent(),
        created_at=timestamp, updated_at=timestamp, revision=1,
    )
    updated = NamespaceState(schema_version=1, nodes={**state.nodes, node.id: node})
    return updated, node.model_copy(deep=True)


def update_node(
    state: NamespaceState, node_id: NodeId, content: ContentRef, expected_revision: int,
) -> tuple[NamespaceState, Node]:
    node = get_node(state, node_id)
    if node.kind != NodeKind.FILE:
        raise WrongNodeKind(str(node_id))
    if node.revision != expected_revision:
        raise RevisionConflict(str(node_id))
    updated_node = node.model_copy(update={
        "content": content.model_copy(deep=True),
        "updated_at": datetime.now(timezone.utc),
        "revision": node.revision + 1,
    }, deep=True)
    updated = NamespaceState(schema_version=1, nodes={**state.nodes, node_id: updated_node})
    return updated, updated_node.model_copy(deep=True)
