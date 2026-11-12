from typing import Annotated, cast

from pydantic import BaseModel, Field as ModelField

from umbod.core.persistence import Field, IntegerCodec, KeyCodec, RowCodec, Table, TableIdentity, TextCodec
from .models import OwnerId, UsageModel


class UsageEventKey(UsageModel):
    event_id: str


class UsageEventRow(UsageEventKey):
    owner_id: OwnerId
    day: int
    otel_json: str


class UsageRollupKey(UsageModel):
    owner_id: OwnerId
    day: int
    kind: Annotated[str, ModelField(pattern=r'^(tool|resource|prompt)$')]
    outcome: Annotated[str, ModelField(pattern=r'^(success|failure|cancelled)$')]


class UsageRollupRow(UsageRollupKey):
    count: Annotated[int, ModelField(ge=1)]


EVENT_IDENTITY = TableIdentity("personal_usage_events")
EVENT_ID = Field[UsageEventRow, str](EVENT_IDENTITY, "event_id", TextCodec())
EVENT_OWNER = Field[UsageEventRow, str](EVENT_IDENTITY, "owner_id", TextCodec())
EVENT_DAY = Field[UsageEventRow, int](EVENT_IDENTITY, "day", IntegerCodec())
EVENT_OTEL = Field[UsageEventRow, str](EVENT_IDENTITY, "otel_json", TextCodec())
EVENT_TABLE = Table(
    EVENT_IDENTITY,
    RowCodec(UsageEventRow, cast(tuple[Field[UsageEventRow, object], ...], (EVENT_ID, EVENT_OWNER, EVENT_DAY, EVENT_OTEL))),
    KeyCodec(UsageEventKey, cast(tuple[Field[UsageEventRow, object], ...], (EVENT_ID,))),
)

ROLLUP_IDENTITY = TableIdentity("personal_usage_daily")
ROLLUP_OWNER = Field[UsageRollupRow, str](ROLLUP_IDENTITY, "owner_id", TextCodec())
ROLLUP_DAY = Field[UsageRollupRow, int](ROLLUP_IDENTITY, "day", IntegerCodec())
ROLLUP_KIND = Field[UsageRollupRow, str](ROLLUP_IDENTITY, "kind", TextCodec())
ROLLUP_OUTCOME = Field[UsageRollupRow, str](ROLLUP_IDENTITY, "outcome", TextCodec())
ROLLUP_COUNT = Field[UsageRollupRow, int](ROLLUP_IDENTITY, "count", IntegerCodec())
ROLLUP_KEY_FIELDS = cast(
    tuple[Field[UsageRollupRow, object], ...],
    (ROLLUP_OWNER, ROLLUP_DAY, ROLLUP_KIND, ROLLUP_OUTCOME),
)
ROLLUP_TABLE = Table(
    ROLLUP_IDENTITY,
    RowCodec(UsageRollupRow, (*ROLLUP_KEY_FIELDS, cast(Field[UsageRollupRow, object], ROLLUP_COUNT))),
    KeyCodec(UsageRollupKey, ROLLUP_KEY_FIELDS),
)
USAGE_TABLES = cast(tuple[Table[BaseModel, BaseModel], ...], (EVENT_TABLE, ROLLUP_TABLE))
