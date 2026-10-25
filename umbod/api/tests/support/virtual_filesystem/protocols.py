from collections.abc import AsyncIterator, Sequence
from datetime import datetime
from typing import Mapping, Optional, Protocol
from uuid import UUID

from umbod.core.virtual_filesystem import EmptyContent, RootParent, UnspecifiedContentType

from .models import (
    ContentHandle,
    Metadata,
    NoContentReference,
    NodeHandle,
    NodeView,
    StoredContentView,
)

ByteStream = AsyncIterator[bytes]


class PublicKind(Protocol):
    value: str


class PublicMetadata(Protocol):
    content_type: str | UnspecifiedContentType
    attributes: Mapping[str, str]


class PublicContentRef(Protocol):
    key: str
    size: int


class PublicNode(Protocol):
    id: UUID
    parent_id: UUID | RootParent
    name: str
    kind: PublicKind
    metadata: PublicMetadata
    content: PublicContentRef | EmptyContent
    created_at: datetime
    updated_at: datetime
    revision: int


class MetadataFactory(Protocol):
    def __call__(
        self, *, content_type: str | UnspecifiedContentType, attributes: dict[str, str]
    ) -> PublicMetadata: ...


class NodeFactory(Protocol):
    def __call__(
        self, *, id: UUID, parent_id: UUID | RootParent, name: str,
        kind: PublicKind, metadata: PublicMetadata, content: PublicContentRef | EmptyContent,
        created_at: datetime, updated_at: datetime, revision: int,
    ) -> PublicNode: ...


class ContentRefFactory(Protocol):
    def __call__(self, *, key: str, size: int) -> PublicContentRef: ...


class NamespacePort(Protocol):
    async def get_root(self) -> PublicNode: ...
    async def get_node(self, node_id: UUID) -> PublicNode: ...
    async def get_child(self, parent_id: UUID, name: str) -> Optional[PublicNode]: ...
    async def list_children(self, parent_id: UUID) -> Sequence[PublicNode]: ...
    async def create_node(
        self, parent_id: UUID, name: str, kind: PublicKind,
        metadata: PublicMetadata,
    ) -> PublicNode: ...
    async def update_node(
        self, node_id: UUID, *, content: PublicContentRef, expected_revision: int,
    ) -> PublicNode: ...


class ContentPort(Protocol):
    async def put(self, data: ByteStream) -> PublicContentRef: ...
    def get(self, key: str) -> ByteStream: ...


class PublicFilesystem(Protocol):
    async def get_root(self) -> PublicNode: ...
    async def create_directory(
        self, parent_id: UUID, name: str, metadata: PublicMetadata,
    ) -> PublicNode: ...
    async def create_file(
        self, parent_id: UUID, name: str, metadata: PublicMetadata,
    ) -> PublicNode: ...
    async def get_node(self, node_id: UUID) -> PublicNode: ...
    async def list_children(self, parent_id: UUID) -> Sequence[PublicNode]: ...
    def read(self, node_id: UUID) -> ByteStream: ...
    async def write(
        self, node_id: UUID, data: ByteStream, *, expected_revision: int,
    ) -> PublicNode: ...


class FilesystemFactory(Protocol):
    def __call__(self, *, namespace: NamespacePort, content: ContentPort) -> PublicFilesystem: ...


class FilesystemLanguage(Protocol):
    async def root(self) -> NodeView: ...
    async def create_directory(
        self, parent: NodeHandle, name: str, metadata: Metadata,
    ) -> NodeView: ...
    async def create_file(
        self, parent: NodeHandle, name: str, metadata: Metadata,
    ) -> NodeView: ...
    async def node(self, node: NodeHandle) -> NodeView: ...
    async def children(self, directory: NodeHandle) -> Sequence[NodeView]: ...
    async def read_file(self, file: NodeHandle) -> bytes: ...
    async def write_file(self, file: NodeHandle, data: bytes, revision: int) -> NodeView: ...


class NamespaceEvidence(Protocol):
    @property
    def creation_calls(self) -> int: ...
    @property
    def root_count(self) -> int: ...


class FilesystemObservations(Protocol):
    async def root_has_no_parent(self) -> bool: ...
    async def content_reference(
        self, node: NodeHandle,
    ) -> StoredContentView | NoContentReference: ...
    async def stored_bytes(self, content: ContentHandle) -> bytes: ...


class PythonFilesystemAcceptancePort(Protocol):
    async def discover_root(self) -> NodeView: ...
    async def create_directory(
        self, parent: NodeHandle, name: str, metadata: Metadata,
    ) -> NodeView: ...
    async def create_file(
        self, parent: NodeHandle, name: str, metadata: Metadata,
    ) -> NodeView: ...
    async def get_node(self, node: NodeHandle) -> NodeView: ...
    async def list_children(self, parent: NodeHandle) -> Sequence[NodeView]: ...
    def read_content(self, node: NodeHandle) -> ByteStream: ...
    async def write_content(
        self, node: NodeHandle, chunks: ByteStream, expected_revision: int,
    ) -> NodeView: ...
    def chunks(self, data: bytes) -> ByteStream: ...
    async def collect(self, chunks: ByteStream) -> bytes: ...
