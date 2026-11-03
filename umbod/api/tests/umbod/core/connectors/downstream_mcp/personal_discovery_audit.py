from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from typing import TypeVar

from pydantic import BaseModel

from umbod.core.configuration.persistence import TextCipher
from umbod.core.connectors.downstream_mcp.stores.personal_discovery_schema import PERSONAL_DISCOVERY_TABLE
from umbod.core.connectors.downstream_mcp.stores.personal_tools_schema import PERSONAL_TOOL_OBSERVATION_TABLE
from umbod.core.persistence import Database, DatabaseSession, Query, ReadSession, Table, TransactionMode

RowT = TypeVar("RowT", bound=BaseModel)
KeyT = TypeVar("KeyT", bound=BaseModel)
ResultT = TypeVar("ResultT", bound=BaseModel)


class DiscoveryReadAudit:
    def __init__(self, delegate: ReadSession) -> None:
        self._delegate = delegate
        self.reads = 0

    async def find_one(self, table: Table[RowT, KeyT], query: Query[RowT, ResultT]) -> ResultT | None:
        assert table in (PERSONAL_DISCOVERY_TABLE, PERSONAL_TOOL_OBSERVATION_TABLE)
        self.reads += 1
        return await self._delegate.find_one(table, query)

    async def find_many(self, table: Table[RowT, KeyT], query: Query[RowT, ResultT]) -> Sequence[ResultT]:
        raise AssertionError("Discovery must be bounded by selected owner connectors")


class AuditedDatabase:
    def __init__(self, delegate: Database, discovery_only: bool) -> None:
        self._delegate = delegate
        self._discovery_only = discovery_only
        self.read_sessions = 0
        self.write_sessions = 0
        self.audits: list[DiscoveryReadAudit] = []

    async def ensure_schema(self, tables: Sequence[Table[BaseModel, BaseModel]]) -> None:
        await self._delegate.ensure_schema(tables)

    @asynccontextmanager
    async def read_session(self) -> AsyncIterator[ReadSession]:
        self.read_sessions += 1
        async with self._delegate.read_session() as session:
            if self._discovery_only:
                audit = DiscoveryReadAudit(session)
                self.audits.append(audit)
                yield audit
            else:
                yield session

    @asynccontextmanager
    async def session(self, *, mode: TransactionMode) -> AsyncIterator[DatabaseSession]:
        assert not self._discovery_only
        self.write_sessions += 1
        async with self._delegate.session(mode=mode) as session:
            yield session


class RestrictedCipher:
    def __init__(self, delegate: TextCipher, permitted: frozenset[str]) -> None:
        self._delegate = delegate
        self._permitted = permitted
        self.decryptions = 0

    def encrypt(self, plaintext: str) -> str:
        raise AssertionError("Discovery must not write")

    def decrypt(self, ciphertext: str) -> str:
        assert ciphertext in self._permitted
        self.decryptions += 1
        return self._delegate.decrypt(ciphertext)
