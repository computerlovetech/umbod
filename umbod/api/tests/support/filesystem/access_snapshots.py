import json
import sqlite3
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import AsyncMock, Mock

from umbod.core.filesystem.errors import StorageFailure
from umbod.core.filesystem.models import AccessGrant, NodeId, Principal
from umbod.core.filesystem.ports import AccessControlDriver
from umbod.core.filesystem.transactions import FilesystemSession, FilesystemTransactions


def corrupt_stored_grant(path: Path, grant: AccessGrant) -> None:
    payload = {**grant.model_dump(mode="json"), "permissions": ["bogus"]}
    with sqlite3.connect(path) as connection:
        changed = connection.execute(
            "UPDATE filesystem_grants SET payload = ? WHERE node_id = ?",
            (json.dumps(payload), str(grant.node_id)),
        )
        assert changed.rowcount == 1


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
