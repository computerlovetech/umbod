from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from umbod.core.persistence import (
    AllFields,
    AllOf,
    Database,
    DatabaseSession,
    DeleteQuery,
    Equals,
    InsertCommand,
    Query,
    TransactionMode,
    Unordered,
    UpsertCommand,
)
from ..errors import InvalidMove, MissingNode, NameCollision, RevisionConflict, StorageFailure, WrongNodeKind
from ..models import ContentRef, Node, NodeId, NodeKind, NodeMetadata, NodeUpdate, RootParent
from ..namespace import (
    ROOT_ID,
    initial_root,
    new_node,
    require_directory,
    updated_node,
    updated_metadata,
    updated_details,
    validate_name,
)
from .schema import (
    NODE_ID, NODE_KEY_PROJECTION, NODE_NAME, NODE_PARENT, NODE_TABLE, NodeKey, NodeRecord,
)
from .session import storage_session
from .discovery_events import append_discovery_changed


def node_record(node: Node) -> NodeRecord:
    return NodeRecord(
        node_id=str(node.id),
        parent_id="" if isinstance(node.parent_id, RootParent) else str(node.parent_id),
        name=node.name,
        revision=node.revision,
        payload=node.model_copy(deep=True),
    )


class DatabaseNamespace:
    def __init__(self, database: Database) -> None:
        self._database = database

    async def _root_exists(self, session: DatabaseSession) -> bool:
        root = await session.find_one(
            NODE_TABLE,
            Query(
                filter=Equals(NODE_ID, str(ROOT_ID)),
                projection=NODE_KEY_PROJECTION,
                ordering=Unordered(),
            ),
        )
        return root is not None

    async def _initialize_root(self, session: DatabaseSession) -> None:
        await SessionNamespace(session).initialize_root()

    @asynccontextmanager
    async def _read_session(self) -> AsyncIterator[DatabaseSession]:
        async with storage_session(self._database, TransactionMode.READ_WRITE) as session:
            if await self._root_exists(session):
                yield session
                return
        async with storage_session(self._database, TransactionMode.SERIALIZED_WRITE) as session:
            await self._initialize_root(session)
            yield session

    async def get_root(self) -> Node:
        return await self.get_node(ROOT_ID)

    async def get_node(self, node_id: NodeId) -> Node:
        async with self._read_session() as session:
            return await SessionNamespace(session).get_node(node_id)

    async def list_children(self, parent_id: NodeId) -> list[Node]:
        async with self._read_session() as session:
            return await SessionNamespace(session).list_children(parent_id)

    async def create_node(
        self, parent_id: NodeId, name: str, kind: NodeKind, metadata: NodeMetadata
    ) -> Node:
        async with storage_session(self._database, TransactionMode.SERIALIZED_WRITE) as session:
            await self._initialize_root(session)
            return await SessionNamespace(session).create_node(parent_id, name, kind, metadata)

    async def update_node(
        self, node_id: NodeId, *, content: ContentRef, expected_revision: int
    ) -> Node:
        async with storage_session(self._database, TransactionMode.SERIALIZED_WRITE) as session:
            await self._initialize_root(session)
            return await SessionNamespace(session).update_node(
                node_id, content=content, expected_revision=expected_revision
            )

    async def update_metadata(
        self, node_id: NodeId, *, metadata: NodeMetadata, expected_revision: int,
    ) -> Node:
        async with storage_session(self._database, TransactionMode.SERIALIZED_WRITE) as session:
            await self._initialize_root(session)
            return await SessionNamespace(session).update_metadata(
                node_id, metadata=metadata, expected_revision=expected_revision,
            )

    async def update_details(
        self, node_id: NodeId, *, details: NodeUpdate, expected_revision: int,
    ) -> Node:
        async with storage_session(self._database, TransactionMode.SERIALIZED_WRITE) as session:
            await self._initialize_root(session)
            return await SessionNamespace(session).update_details(
                node_id, details=details, expected_revision=expected_revision,
            )

    async def delete_node(self, node_id: NodeId, *, expected_revision: int) -> None:
        async with storage_session(self._database, TransactionMode.SERIALIZED_WRITE) as session:
            await SessionNamespace(session).delete_node(node_id, expected_revision=expected_revision)


class SessionNamespace:
    def __init__(self, session: DatabaseSession) -> None:
        self._session = session

    async def update_metadata(
        self, node_id: NodeId, *, metadata: NodeMetadata, expected_revision: int,
    ) -> Node:
        node = updated_metadata(await self.get_node(node_id), metadata, expected_revision)
        await self._session.upsert(
            NODE_TABLE, UpsertCommand(key=NodeKey(node_id=str(node_id)), row=node_record(node)),
        )
        return node.model_copy(deep=True)

    async def update_details(
        self, node_id: NodeId, *, details: NodeUpdate, expected_revision: int,
    ) -> Node:
        previous = await self.get_node(node_id)
        node = updated_details(previous, details, expected_revision)
        placement_changed = node.name != previous.name or node.parent_id != previous.parent_id
        if placement_changed:
            if isinstance(node.parent_id, RootParent):
                raise InvalidMove()
            await self._validate_destination(node_id, node.parent_id)
            existing = await self._session.find_one(
                NODE_TABLE,
                Query(
                    filter=AllOf((Equals(NODE_PARENT, str(node.parent_id)), Equals(NODE_NAME, node.name))),
                    projection=AllFields(), ordering=Unordered(),
                ),
            )
            if existing is not None and existing.payload.id != node_id:
                raise NameCollision(node.name)
        await self._session.upsert(
            NODE_TABLE, UpsertCommand(key=NodeKey(node_id=str(node_id)), row=node_record(node)),
        )
        if placement_changed:
            await append_discovery_changed(self._session)
        return node.model_copy(deep=True)

    async def _validate_destination(self, node_id: NodeId, parent_id: NodeId) -> None:
        parent = require_directory(await self.get_node(parent_id))
        visited: set[NodeId] = set()
        while True:
            if parent.id == node_id:
                raise InvalidMove()
            if parent.id in visited:
                raise StorageFailure("Invalid filesystem hierarchy")
            visited.add(parent.id)
            if parent.id == ROOT_ID:
                if not isinstance(parent.parent_id, RootParent) or parent.name != "":
                    raise StorageFailure("Invalid filesystem root")
                return
            if isinstance(parent.parent_id, RootParent):
                raise StorageFailure("Invalid filesystem hierarchy")
            try:
                parent = await self.get_node(parent.parent_id)
            except MissingNode:
                raise StorageFailure("Invalid filesystem hierarchy") from None
            if parent.kind != NodeKind.DIRECTORY:
                raise StorageFailure("Invalid filesystem hierarchy")

    async def delete_node(self, node_id: NodeId, *, expected_revision: int) -> None:
        node = await self.get_node(node_id)
        if node.kind != NodeKind.FILE:
            raise WrongNodeKind(str(node_id))
        if node.revision != expected_revision:
            raise RevisionConflict(str(node_id))
        await self._session.delete(NODE_TABLE, DeleteQuery(filter=Equals(NODE_ID, str(node_id))))
        await append_discovery_changed(self._session)

    async def initialize_root(self) -> None:
        record = await self._session.find_one(
            NODE_TABLE,
            Query(filter=Equals(NODE_ID, str(ROOT_ID)), projection=NODE_KEY_PROJECTION, ordering=Unordered()),
        )
        if record is None:
            await self._session.insert(NODE_TABLE, InsertCommand(row=node_record(initial_root())))
            await append_discovery_changed(self._session)

    async def get_node(self, node_id: NodeId) -> Node:
        record = await self._session.find_one(
            NODE_TABLE,
            Query(
                filter=Equals(NODE_ID, str(node_id)),
                projection=AllFields(),
                ordering=Unordered(),
            ),
        )
        if record is None:
            raise MissingNode(str(node_id))
        return record.payload.model_copy(deep=True)

    async def get_root(self) -> Node:
        return await self.get_node(ROOT_ID)

    async def list_children(self, parent_id: NodeId) -> list[Node]:
        require_directory(await self.get_node(parent_id))
        records = await self._session.find_many(
            NODE_TABLE,
            Query(
                filter=Equals(NODE_PARENT, str(parent_id)),
                projection=AllFields(),
                ordering=Unordered(),
            ),
        )
        return sorted(
            (record.payload.model_copy(deep=True) for record in records),
            key=lambda node: node.name,
        )

    async def create_node(
        self,
        parent_id: NodeId,
        name: str,
        kind: NodeKind,
        metadata: NodeMetadata,
    ) -> Node:
        require_directory(await self.get_node(parent_id))
        validate_name(name)
        existing = await self._session.find_one(
            NODE_TABLE,
            Query(
                filter=AllOf(
                    (Equals(NODE_PARENT, str(parent_id)), Equals(NODE_NAME, name))
                ),
                projection=AllFields(),
                ordering=Unordered(),
            ),
        )
        if existing is not None:
            raise NameCollision(name)
        node = new_node(parent_id, name, kind, metadata)
        if not await self._session.insert(
            NODE_TABLE, InsertCommand(row=node_record(node))
        ):
            raise NameCollision(name)
        await append_discovery_changed(self._session)
        return node.model_copy(deep=True)

    async def update_node(
        self,
        node_id: NodeId,
        *,
        content: ContentRef,
        expected_revision: int,
    ) -> Node:
        node = updated_node(
            await self.get_node(node_id), content, expected_revision
        )
        await self._session.upsert(
            NODE_TABLE,
            UpsertCommand(key=NodeKey(node_id=str(node_id)), row=node_record(node)),
        )
        return node.model_copy(deep=True)
