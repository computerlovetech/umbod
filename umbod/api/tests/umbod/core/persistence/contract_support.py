import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from pydantic import BaseModel, ConfigDict

from umbod.core.persistence import (
    AllFields,
    BooleanCodec,
    ColumnType,
    Database,
    Field,
    IntegerCodec,
    InsertCommand,
    JsonTupleCodec,
    JsonValueCodec,
    KeyCodec,
    NoFilter,
    PydanticJsonCodec,
    Query,
    RowCodec,
    Table,
    TableIdentity,
    TextCodec,
    TransactionMode,
    Unordered,
    UpsertCommand,
)
from tests.persistence_runtime import create_inmemory_runtime, create_sqlite_runtime

class SampleRow(BaseModel):
    model_config = ConfigDict(frozen=True)
    owner_id: str
    record_id: str
    payload: str

class SampleKey(BaseModel):
    model_config = ConfigDict(frozen=True)
    owner_id: str
    record_id: str

class PayloadResult(BaseModel):
    model_config = ConfigDict(frozen=True)
    payload: str

class RecordResult(BaseModel):
    model_config = ConfigDict(frozen=True)
    record_id: str

class SampleDocument(BaseModel):
    model_config = ConfigDict(frozen=True)
    label: str

class CanonicalRow(BaseModel):
    model_config = ConfigDict(frozen=True)
    record_id: str
    enabled: bool
    payload: object
    labels: tuple[str, ...]
    document: SampleDocument

class CanonicalKey(BaseModel):
    model_config = ConfigDict(frozen=True)
    record_id: str

class GeneratedRow(BaseModel):
    model_config = ConfigDict(frozen=True)
    sequence: int
    payload: str

class GeneratedKey(BaseModel):
    model_config = ConfigDict(frozen=True)
    sequence: int

class NullableTextCodec:
    column_type = ColumnType.NULLABLE_TEXT

    def encode(self, value: str | None) -> object:
        if value is not None and (not isinstance(value, str)):
            raise TypeError('expected str or None')
        return value

    def decode(self, value: object) -> str | None:
        if value is not None and (not isinstance(value, str)):
            raise TypeError('expected stored text or None')
        return value

class ScalarRow(BaseModel):
    model_config = ConfigDict(frozen=True)
    record_id: str
    number: int
    enabled: bool
    optional_text: str | None

class ScalarKey(BaseModel):
    model_config = ConfigDict(frozen=True)
    record_id: str


class ScalarValuesResult(BaseModel):
    model_config = ConfigDict(frozen=True, strict=True)
    number: int
    enabled: bool


DatabaseFactory = Callable[[Path], Database]


@dataclass(frozen=True)
class DatabaseAdapter:
    name: str
    factory: DatabaseFactory


def _inmemory(_path: Path) -> Database:
    return create_inmemory_runtime().database


def _sqlite(path: Path) -> Database:
    return create_sqlite_runtime(path / 'contract.sqlite').database


DATABASE_ADAPTERS = (
    DatabaseAdapter('inmemory', _inmemory),
    DatabaseAdapter('sqlite', _sqlite),
)


async def serialized_claim_observations(
    first_database: Database, second_database: Database,
) -> tuple[str, ...]:
    contract_table, _, _, _ = table("serialized_claims")
    await first_database.ensure_schema((contract_table,))
    async with first_database.session(mode=TransactionMode.READ_WRITE) as session:
        await session.insert(contract_table, InsertCommand(row=row("shared", "available")))
    first_read = asyncio.Event()
    contender_started = asyncio.Event()
    contender_read = asyncio.Event()

    async def claim(database: Database, first: bool) -> str:
        if not first:
            await first_read.wait()
            contender_started.set()
        async with database.session(mode=TransactionMode.SERIALIZED_WRITE) as session:
            existing = await session.find_one(
                contract_table, Query(NoFilter(), AllFields(), Unordered()),
            )
            if existing is None:
                raise AssertionError("Seeded claim row is missing")
            if first:
                first_read.set()
                await contender_started.wait()
                try:
                    await asyncio.wait_for(contender_read.wait(), timeout=0.1)
                except TimeoutError:
                    pass
            else:
                contender_read.set()
            if existing.payload == "available":
                await session.upsert(
                    contract_table,
                    UpsertCommand(
                        key=SampleKey(owner_id="owner", record_id="shared"),
                        row=row("shared", "claimed"),
                    ),
                )
            return existing.payload

    tasks = (
        asyncio.create_task(claim(first_database, True)),
        asyncio.create_task(claim(second_database, False)),
    )
    try:
        return tuple(await asyncio.wait_for(asyncio.gather(*tasks), timeout=10))
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

def table(name: str='typed_samples') -> tuple[Table[SampleRow, SampleKey], Field[SampleRow, str], Field[SampleRow, str], Field[SampleRow, str]]:
    identity = TableIdentity(name)
    owner = Field[SampleRow, str](identity, 'owner_id', TextCodec())
    record = Field[SampleRow, str](identity, 'record_id', TextCodec())
    payload = Field[SampleRow, str](identity, 'payload', TextCodec())
    fields = cast(tuple[Field[SampleRow, object], ...], (owner, record, payload))
    keys = cast(tuple[Field[SampleRow, object], ...], (owner, record))
    return (Table(identity, RowCodec(SampleRow, fields), KeyCodec(SampleKey, keys)), owner, record, payload)

def row(record_id: str, payload: str='same') -> SampleRow:
    return SampleRow(owner_id='owner', record_id=record_id, payload=payload)

def generated_table(name: str='generated_samples') -> tuple[Table[GeneratedRow, GeneratedKey], Field[GeneratedRow, int]]:
    identity = TableIdentity(name)
    sequence = Field[GeneratedRow, int](identity, 'sequence', IntegerCodec())
    payload = Field[GeneratedRow, str](identity, 'payload', TextCodec())
    fields = cast(tuple[Field[GeneratedRow, object], ...], (sequence, payload))
    keys = cast(tuple[Field[GeneratedRow, object], ...], (sequence,))
    return (Table(identity, RowCodec(GeneratedRow, fields), KeyCodec(GeneratedKey, keys)), sequence)

def canonical_table(name: str='canonical_samples') -> Table[CanonicalRow, CanonicalKey]:
    identity = TableIdentity(name)
    fields = cast(tuple[Field[CanonicalRow, object], ...], (Field[CanonicalRow, str](identity, 'record_id', TextCodec()), Field[CanonicalRow, bool](identity, 'enabled', BooleanCodec()), Field[CanonicalRow, object](identity, 'payload', JsonValueCodec()), Field[CanonicalRow, tuple[str, ...]](identity, 'labels', JsonTupleCodec()), Field[CanonicalRow, SampleDocument](identity, 'document', PydanticJsonCodec(SampleDocument))))
    return Table(identity, RowCodec(CanonicalRow, fields), KeyCodec(CanonicalKey, (fields[0],)))

def scalar_table(name: str='scalar_samples') -> Table[ScalarRow, ScalarKey]:
    identity = TableIdentity(name)
    fields = cast(tuple[Field[ScalarRow, object], ...], (Field[ScalarRow, str](identity, 'record_id', TextCodec()), Field[ScalarRow, int](identity, 'number', IntegerCodec()), Field[ScalarRow, bool](identity, 'enabled', BooleanCodec()), Field[ScalarRow, str | None](identity, 'optional_text', NullableTextCodec())))
    return Table(identity, RowCodec(ScalarRow, fields), KeyCodec(ScalarKey, (fields[0],)))
