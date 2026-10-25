# Umbod Virtual Filesystem — Driver Design (v0.1)

## Goal

Provide a storage-agnostic virtual filesystem with nested directories and files. Logical organization and metadata are independent of the storage of file bytes. Concrete drivers (e.g. local filesystem, S3) are out of scope.

## Architecture

```mermaid
flowchart TD
    Client[Caller / future MCP adapter] --> VFS[VirtualFilesystem service]
    VFS --> NS[NamespaceDriver protocol]
    VFS --> CD[ContentDriver protocol]
    NS -. implements .-> N[Namespace backend]
    CD -. implements .-> C[Content backend]
```

The service coordinates metadata and content operations. Drivers do not depend on one another.

## Models (Pydantic v2)

```python
from datetime import datetime
from enum import StrEnum
from uuid import UUID
from pydantic import BaseModel, Field

NodeId = UUID
StorageKey = str

class NodeKind(StrEnum):
    FILE = "file"
    DIRECTORY = "directory"

class ContentRef(BaseModel):
    key: StorageKey  # opaque, immutable content object
    size: int = Field(ge=0)
    checksum: str | None = None

class NodeMetadata(BaseModel):
    content_type: str | None = None
    attributes: dict[str, str] = Field(default_factory=dict)

class Node(BaseModel):
    id: NodeId
    parent_id: NodeId | None
    name: str
    kind: NodeKind
    metadata: NodeMetadata = Field(default_factory=NodeMetadata)
    content: ContentRef | None = None
    created_at: datetime
    updated_at: datetime
    revision: int = Field(ge=1)
```

Paths are derived from `parent_id` and `name`; a node's ID survives moves and renames. Only files may have content references.

## Low-level protocols

```python
from collections.abc import AsyncIterator, Sequence
from typing import Protocol

ByteStream = AsyncIterator[bytes]

class NamespaceDriver(Protocol):
    async def get_node(self, node_id: NodeId) -> Node: ...
    async def get_child(self, parent_id: NodeId, name: str) -> Node | None: ...
    async def list_children(self, parent_id: NodeId) -> Sequence[Node]: ...
    async def create_node(
        self, parent_id: NodeId, name: str, kind: NodeKind,
        metadata: NodeMetadata | None = None,
        content: ContentRef | None = None,
    ) -> Node: ...
    async def update_node(
        self, node_id: NodeId, *,
        metadata: NodeMetadata | None = None,
        content: ContentRef | None = None,
        expected_revision: int,
    ) -> Node: ...
    async def move_node(
        self, node_id: NodeId, new_parent_id: NodeId, new_name: str,
        *, expected_revision: int,
    ) -> Node: ...
    async def delete_node(
        self, node_id: NodeId, *, expected_revision: int,
    ) -> None: ...

class ContentDriver(Protocol):
    async def put(self, data: ByteStream) -> ContentRef: ...
    def get(self, key: StorageKey) -> ByteStream: ...
    async def delete(self, key: StorageKey) -> None: ...
```

`update_node` is provisional: before implementation, use an explicit patch model or sentinel to distinguish omitted fields from clearing a content reference.

## Write lifecycle

```mermaid
sequenceDiagram
    participant Caller
    participant VFS as VirtualFilesystem
    participant Content as ContentDriver
    participant NS as NamespaceDriver
    Caller->>VFS: write(node_id, bytes, expected_revision)
    VFS->>NS: get_node(node_id)
    NS-->>VFS: Node
    VFS->>Content: put(byte stream)
    Content-->>VFS: new ContentRef
    VFS->>NS: update_node(content ref, expected_revision)
    alt revision matches
        NS-->>VFS: updated Node
        VFS-->>Caller: updated Node
    else conflict
        NS-->>VFS: RevisionConflict
        Note over VFS,Content: Unreferenced object eligible for safe GC
        VFS-->>Caller: RevisionConflict
    end
```

Content objects are immutable. Replacing a file creates a new object and atomically updates its namespace reference. Unreferenced objects require deferred, concurrency-safe garbage collection.

## Required invariants

- Exactly one root (`parent_id=None`); root cannot be moved or deleted.
- Names are single path components; sibling names are unique.
- Parents must exist and be directories; moves cannot create cycles.
- Directories have no content; files may initially have none.
- Deleting a nonempty directory fails; recursive deletion is not part of v0.1.
- Namespace mutations are atomic and use optimistic revision checks.
- A successful content `put` yields a complete, readable object.

## Out of scope

Authorization, OAuth groups, CapabilitySets, MCP exposure, concrete adapters, symlinks, recursive deletion, locking, notifications, indexing, and cross-driver transactions.
