from collections import Counter
from collections.abc import Sequence
from typing import TypeVar

from pydantic import BaseModel

from umbod.core.persistence.ports import ReadSession
from umbod.core.persistence.query import Query, Table

RowT = TypeVar("RowT", bound=BaseModel)
KeyT = TypeVar("KeyT", bound=BaseModel)
ResultT = TypeVar("ResultT", bound=BaseModel)


class RecordingReadSession:
    def __init__(self, session: ReadSession) -> None:
        self._session = session
        self.find_one_calls: int = 0
        self.find_many_calls: int = 0
        self.find_many_tables: Counter[str] = Counter()

    async def find_one(
        self, table: Table[RowT, KeyT], query: Query[RowT, ResultT]
    ) -> ResultT | None:
        self.find_one_calls += 1
        return await self._session.find_one(table, query)

    async def find_many(
        self, table: Table[RowT, KeyT], query: Query[RowT, ResultT]
    ) -> Sequence[ResultT]:
        self.find_many_calls += 1
        self.find_many_tables[table.name] += 1
        return await self._session.find_many(table, query)
