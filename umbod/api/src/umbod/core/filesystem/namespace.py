from datetime import datetime, timezone
from uuid import UUID, uuid4

from .errors import InvalidMove, InvalidName, RevisionConflict, RootMutation, WrongNodeKind
from .models import (
    ContentRef,
    EmptyContent,
    Node,
    NodeId,
    NodeKind,
    NodeMetadata,
    NodeUpdate,
    RootParent,
    UnspecifiedContentType,
)

ROOT_ID = UUID(int=0)


def valid_name(name: str) -> bool:
    try:
        name.encode("utf-8")
    except UnicodeEncodeError:
        return False
    return name not in ("", ".", "..") and not any(
        character in name for character in ("/", "\\", "\0")
    )


def initial_root() -> Node:
    timestamp = datetime.now(timezone.utc)
    return Node(
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


def require_directory(node: Node) -> Node:
    if node.kind != NodeKind.DIRECTORY:
        raise WrongNodeKind(str(node.id))
    return node


def validate_name(name: str) -> None:
    if not valid_name(name):
        raise InvalidName(name)


def new_node(
    parent_id: NodeId, name: str, kind: NodeKind, metadata: NodeMetadata
) -> Node:
    validate_name(name)
    timestamp = datetime.now(timezone.utc)
    return Node(
        id=uuid4(),
        parent_id=parent_id,
        name=name,
        kind=kind,
        metadata=metadata.model_copy(deep=True),
        content=EmptyContent(),
        created_at=timestamp,
        updated_at=timestamp,
        revision=1,
    )


def updated_metadata(node: Node, metadata: NodeMetadata, expected_revision: int) -> Node:
    if node.revision != expected_revision:
        raise RevisionConflict(str(node.id))
    return node.model_copy(
        update={
            "metadata": metadata.model_copy(deep=True),
            "updated_at": datetime.now(timezone.utc),
            "revision": node.revision + 1,
        },
        deep=True,
    )


def updated_details(node: Node, details: NodeUpdate, expected_revision: int) -> Node:
    updated = updated_metadata(node, details.metadata, expected_revision)
    if node.id == ROOT_ID:
        if details.name != node.name or details.parent_id != node.parent_id:
            raise RootMutation()
    else:
        validate_name(details.name)
        if isinstance(details.parent_id, RootParent):
            raise InvalidMove()
    return updated.model_copy(update={"name": details.name, "parent_id": details.parent_id}, deep=True)


def updated_node(node: Node, content: ContentRef, expected_revision: int) -> Node:
    if node.kind != NodeKind.FILE:
        raise WrongNodeKind(str(node.id))
    if node.revision != expected_revision:
        raise RevisionConflict(str(node.id))
    return node.model_copy(
        update={
            "content": content.model_copy(deep=True),
            "updated_at": datetime.now(timezone.utc),
            "revision": node.revision + 1,
        },
        deep=True,
    )
