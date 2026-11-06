from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from typing import TypeVar
from unittest.mock import AsyncMock, Mock

import pytest
from pydantic import BaseModel

from umbod.core.filesystem.errors import StorageFailure
from umbod.core.filesystem.models import NodeId, Principal
from umbod.core.filesystem.ports import AccessControlDriver
from umbod.core.filesystem.transactions import FilesystemSession, FilesystemTransactions


from umbod.core.filesystem.stores.schema import GRANT_TABLE, GrantRecord
from umbod.core.persistence import Database, DatabaseSession, PersistenceDecodingError, Query, Table, TransactionMode

RowT = TypeVar("RowT", bound=BaseModel)
KeyT = TypeVar("KeyT", bound=BaseModel)
ResultT = TypeVar("ResultT", bound=BaseModel)


def fail_stored_grant_decoding(database: Database, node_id: NodeId, monkeypatch: pytest.MonkeyPatch) -> None:
    original_session = database.session

    @asynccontextmanager
    async def failing_session(*, mode: TransactionMode) -> AsyncIterator[DatabaseSession]:
        async with original_session(mode=mode) as session:
            async def find_many(table: Table[RowT, KeyT], query: Query[RowT, ResultT]) -> Sequence[ResultT]:
                rows = await session.find_many(table, query)
                if table == GRANT_TABLE and any(
                    isinstance(row, GrantRecord) and row.node_id == str(node_id) for row in rows
                ):
                    raise PersistenceDecodingError(table.name, "payload", ValueError("Invalid stored grant"))
                return rows

            failing = Mock(spec=DatabaseSession, wraps=session)
            failing.find_many.side_effect = find_many
            yield failing

    monkeypatch.setattr(database, "session", failing_session)


class RevokeAfterCommitTransactions:
    def __init__(
        self, transactions: FilesystemTransactions, policies: AccessControlDriver,
        node_id: NodeId, principal: Principal,
    ) -> None:
        self._transactions = transactions
        self._policies = policies
        self._node_id = node_id
        self._principal = principal

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[FilesystemSession]:
        async with self._transactions.transaction() as session:
            yield session
        await self._policies.remove_grant(self._node_id, self._principal)


class FailingGrantReadTransactions:
    def __init__(self, transactions: FilesystemTransactions) -> None:
        self._transactions = transactions

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[FilesystemSession]:
        async with self._transactions.transaction() as session:
            policies = Mock(spec=AccessControlDriver, wraps=session.access_control)
            policies.list_grants = AsyncMock(side_effect=StorageFailure("Database I/O failed"))
            yield FilesystemSession(session.namespace, policies)
