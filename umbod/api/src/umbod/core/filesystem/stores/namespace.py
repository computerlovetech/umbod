from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from umbod.core.persistence import (
    AllFields,
    AllOf,
    Database,
    DatabaseSession,
    Equals,
    InsertCommand,
    Query,
    TransactionMode,
    Unordered,
    UpsertCommand,
)
from ..errors import MissingNode, NameCollision
from ..models import ContentRef, Node, NodeId, NodeKind, NodeMetadata, RootParent
from ..namespace import (
    ROOT_ID,
    initial_root,
    new_node,
    require_directory,
    updated_node,
    validate_name,
)
from .schema import (
    NODE_ID, NODE_KEY_PROJECTION, NODE_NAME, NODE_PARENT, NODE_TABLE, NodeKey, NodeRecord,
)
from .session import storage_session


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
        if not await self._root_exists(session):
            await session.insert(NODE_TABLE, InsertCommand(row=node_record(initial_root())))

    @asynccontextmanager
    async def _read_session(self) -> AsyncIterator[DatabaseSession]:
        async with storage_session(self._database, TransactionMode.READ_WRITE) as session:
            if await self._root_exists(session):
                yield session
                return
        async with storage_session(self._database, TransactionMode.SERIALIZED_WRITE) as session:
            await self._initialize_root(session)
            yield session

    async def _get_node(self, session: DatabaseSession, node_id: NodeId) -> Node:
        record = await session.find_one(
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

    async def get_node(self, node_id: NodeId) -> Node:
        async with self._read_session() as session:
            return await self._get_node(session, node_id)

    async def list_children(self, parent_id: NodeId) -> list[Node]:
        async with self._read_session() as session:
            require_directory(await self._get_node(session, parent_id))
            records = await session.find_many(
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
        async with storage_session(
            self._database, TransactionMode.SERIALIZED_WRITE
        ) as session:
            await self._initialize_root(session)
            require_directory(await self._get_node(session, parent_id))
            validate_name(name)
            existing = await session.find_one(
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
            if not await session.insert(
                NODE_TABLE, InsertCommand(row=node_record(node))
            ):
                raise NameCollision(name)
            return node.model_copy(deep=True)

    async def update_node(
        self,
        node_id: NodeId,
        *,
        content: ContentRef,
        expected_revision: int,
    ) -> Node:
        async with storage_session(
            self._database, TransactionMode.SERIALIZED_WRITE
        ) as session:
            await self._initialize_root(session)
            node = updated_node(
                await self._get_node(session, node_id), content, expected_revision
            )
            await session.upsert(
                NODE_TABLE,
                UpsertCommand(key=NodeKey(node_id=str(node_id)), row=node_record(node)),
            )
            return node.model_copy(deep=True)
