from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from unittest.mock import create_autospec

from umbod.core.filesystem import (
    FilesystemSession, FilesystemTransactions, NamespaceDriver, Node, NodeId, NodeKind, NodeMetadata,
)


class RecordingTransactions:
    def __init__(self, transactions: FilesystemTransactions) -> None:
        self._transactions = transactions
        self.created: list[NodeId] = []

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[FilesystemSession]:
        async with self._transactions.transaction() as session:
            namespace = create_autospec(NamespaceDriver, instance=True)
            namespace.get_node.side_effect = session.namespace.get_node

            async def create(parent_id: NodeId, name: str, kind: NodeKind, metadata: NodeMetadata) -> Node:
                node = await session.namespace.create_node(parent_id, name, kind, metadata)
                self.created.append(node.id)
                return node

            namespace.create_node.side_effect = create
            yield FilesystemSession(namespace=namespace, access_control=session.access_control)
