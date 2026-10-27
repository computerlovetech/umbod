from dataclasses import dataclass
from typing import Generic, Literal, Optional, Protocol, TypeVar, cast, overload

from pydantic import BaseModel

from umbod.core.persistence.ports import DatabaseSession
from umbod.core.persistence.query import Query, Table, validate_query

RowT = TypeVar("RowT", bound=BaseModel)
KeyT = TypeVar("KeyT", bound=BaseModel)
ResultT = TypeVar("ResultT", bound=BaseModel)


@dataclass(frozen=True, eq=False)
class ManyRead(Generic[ResultT]):
    _owner: object


@dataclass(frozen=True, eq=False)
class OneRead(Generic[ResultT]):
    _owner: object


class ReadResults:
    def __init__(
        self,
        owner: object,
        values: dict[ManyRead[BaseModel] | OneRead[BaseModel], object],
    ) -> None:
        self._owner = owner
        self._values = dict(values)

    @overload
    def get(self, handle: ManyRead[ResultT]) -> tuple[ResultT, ...]: ...

    @overload
    def get(self, handle: OneRead[ResultT]) -> Optional[ResultT]: ...

    def get(
        self, handle: ManyRead[ResultT] | OneRead[ResultT]
    ) -> tuple[ResultT, ...] | Optional[ResultT]:
        if handle._owner is not self._owner:
            raise ValueError("Read handle belongs to another plan")
        return cast(tuple[ResultT, ...] | Optional[ResultT], self._values[handle])


class ReadPlanOperations(Protocol):
    def find_many(
        self, table: Table[RowT, KeyT], query: Query[RowT, ResultT]
    ) -> ManyRead[ResultT]: ...

    def find_one(
        self, table: Table[RowT, KeyT], query: Query[RowT, ResultT]
    ) -> OneRead[ResultT]: ...

    async def execute(self, session: DatabaseSession) -> ReadResults: ...


@dataclass(frozen=True)
class _Read:
    table: Table[BaseModel, BaseModel]
    query: Query[BaseModel, BaseModel]
    cardinality: Literal["many", "one"]

    async def run(self, session: DatabaseSession) -> object:
        if self.cardinality == "many":
            return tuple(await session.find_many(self.table, self.query))
        return await session.find_one(self.table, self.query)


@dataclass(frozen=True)
class _OptimizedReads:
    reads: tuple[_Read, ...]
    result_indices: tuple[int, ...]

    async def run(self, session: DatabaseSession) -> tuple[object, ...]:
        values: list[object] = []
        for read in self.reads:
            values.append(await read.run(session))
        return tuple(values[index] for index in self.result_indices)


def _optimize(reads: tuple[_Read, ...]) -> _OptimizedReads:
    unique: list[_Read] = []
    indices: list[int] = []
    for read in reads:
        try:
            index = unique.index(read)
        except ValueError:
            index = len(unique)
            unique.append(read)
        indices.append(index)
    return _OptimizedReads(tuple(unique), tuple(indices))


class ReadPlan:
    def __init__(self) -> None:
        self._owner = object()
        self._frozen = False
        self._reads: list[_Read] = []
        self._handles: list[ManyRead[BaseModel] | OneRead[BaseModel]] = []

    def find_many(
        self, table: Table[RowT, KeyT], query: Query[RowT, ResultT]
    ) -> ManyRead[ResultT]:
        handle = ManyRead[ResultT](self._owner)
        self._register(table, query, "many", handle)
        return handle

    def find_one(
        self, table: Table[RowT, KeyT], query: Query[RowT, ResultT]
    ) -> OneRead[ResultT]:
        handle = OneRead[ResultT](self._owner)
        self._register(table, query, "one", handle)
        return handle

    def _register(
        self,
        table: Table[RowT, KeyT],
        query: Query[RowT, ResultT],
        cardinality: Literal["many", "one"],
        handle: ManyRead[ResultT] | OneRead[ResultT],
    ) -> None:
        if self._frozen:
            raise RuntimeError("Read plan registration is frozen")
        validate_query(table, query)
        self._reads.append(
            _Read(
                cast(Table[BaseModel, BaseModel], table),
                cast(Query[BaseModel, BaseModel], query),
                cardinality,
            )
        )
        self._handles.append(cast(ManyRead[BaseModel] | OneRead[BaseModel], handle))

    async def execute(self, session: DatabaseSession) -> ReadResults:
        self._frozen = True
        optimized = _optimize(tuple(self._reads))
        values = await optimized.run(session)
        return ReadResults(self._owner, dict(zip(self._handles, values, strict=True)))
