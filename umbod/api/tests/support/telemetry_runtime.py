import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import cast

from pydantic import BaseModel, ConfigDict, ValidationError

from umbod.core.persistence import (
    AllFields,
    Database,
    Field,
    GeneratedIntegerKeyInsertCommand,
    IntegerCodec,
    NoFilter,
    NonReusingIntegerKeyCodec,
    OrderBy,
    PersistenceReadiness,
    PydanticJsonCodec,
    Query,
    RowCodec,
    Table,
    TableIdentity,
    TransactionMode,
)
from umbod.core.telemetry.analytics import (
    AnalyticsLogRecord,
    LogCountQuery,
    LogCountResult,
    LogWriteBatch,
    OwnedLog,
    PresentDimensionValue,
    TelemetryAnalyticsReader,
    TelemetryAnalyticsUnavailable,
    TelemetryAnalyticsWriter,
)

from tests.support.telemetry_analytics import (
    InMemoryTelemetryAnalyticsReader,
    NormalizedLog,
)


class _LogRow(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    sequence: int
    record: AnalyticsLogRecord


class _LogKey(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    sequence: int


_IDENTITY = TableIdentity("_test_telemetry_analytics_logs")
_SEQUENCE = Field[_LogRow, int](_IDENTITY, "sequence", IntegerCodec())
_RECORD = Field[_LogRow, AnalyticsLogRecord](
    _IDENTITY, "record", PydanticJsonCodec(AnalyticsLogRecord)
)
_TABLE = Table(
    _IDENTITY,
    RowCodec(_LogRow, cast(tuple[Field[_LogRow, object], ...], (_SEQUENCE, _RECORD))),
    NonReusingIntegerKeyCodec(
        _LogKey, cast(tuple[Field[_LogRow, object], ...], (_SEQUENCE,))
    ),
)


class InMemoryTelemetryAnalyticsRuntime:
    def __init__(self, database: Database, readiness: PersistenceReadiness) -> None:
        self._database = database
        self._readiness = readiness
        self._lock = asyncio.Lock()
        self._closed = False
        self._ready = False

    @asynccontextmanager
    async def operation(self) -> AsyncIterator[Database]:
        async with self._lock:
            if self._closed:
                raise TelemetryAnalyticsUnavailable("Telemetry analytics is unavailable")
            try:
                if not self._ready:
                    await self._readiness.ensure_ready()
                    await self._database.ensure_schema(
                        (cast(Table[BaseModel, BaseModel], _TABLE),)
                    )
                    self._ready = True
                yield self._database
            except (OSError, RuntimeError, ValueError, TypeError, OverflowError):
                raise TelemetryAnalyticsUnavailable(
                    "Telemetry analytics is unavailable"
                ) from None

    async def ensure_ready(self) -> None:
        async with self.operation():
            pass

    async def shutdown(self) -> None:
        async with self._lock:
            self._closed = True

    def create_reader(self) -> TelemetryAnalyticsReader:
        return _Reader(self)

    def create_writer(self) -> TelemetryAnalyticsWriter:
        return _Writer(self)


class _Writer:
    def __init__(self, runtime: InMemoryTelemetryAnalyticsRuntime) -> None:
        self._runtime = runtime

    async def append_logs(self, batch: LogWriteBatch) -> None:
        try:
            validated = LogWriteBatch.model_validate(batch.model_dump())
        except ValidationError:
            raise TelemetryAnalyticsUnavailable(
                "Telemetry analytics is unavailable"
            ) from None
        async with self._runtime.operation() as database:
            async with database.session(mode=TransactionMode.SERIALIZED_WRITE) as session:
                for record in validated.records:
                    await session.insert_generated_integer_key(
                        _TABLE,
                        GeneratedIntegerKeyInsertCommand(
                            _LogRow(sequence=0, record=record), _SEQUENCE
                        ),
                    )


class _Reader:
    def __init__(self, runtime: InMemoryTelemetryAnalyticsRuntime) -> None:
        self._runtime = runtime

    async def count_logs(self, query: LogCountQuery) -> LogCountResult:
        try:
            validated = LogCountQuery.model_validate(query.model_dump())
        except ValidationError:
            raise TelemetryAnalyticsUnavailable(
                "Telemetry analytics is unavailable"
            ) from None
        async with self._runtime.operation() as database:
            selection: Query[_LogRow, _LogRow] = Query(
                filter=NoFilter(),
                projection=AllFields(),
                ordering=OrderBy(
                    cast(tuple[Field[_LogRow, object], ...], (_SEQUENCE,))
                ),
            )
            async with database.read_session() as session:
                rows = await session.find_many(_TABLE, selection)
            logs = tuple(
                NormalizedLog(
                    occurred_at=row.record.occurred_at,
                    owner_id=(
                        row.record.owner.owner_id
                        if isinstance(row.record.owner, OwnedLog)
                        else None
                    ),
                    dimensions={
                        group.dimension: group.value.value
                        for group in row.record.dimensions
                        if isinstance(group.value, PresentDimensionValue)
                    },
                )
                for row in rows
            )
            return await InMemoryTelemetryAnalyticsReader(logs).count_logs(validated)
