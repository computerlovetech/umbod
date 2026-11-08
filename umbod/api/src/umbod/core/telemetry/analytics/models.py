from datetime import datetime, timezone
from enum import Enum
from typing import Annotated, Literal, Self

from pydantic import (
    AfterValidator,
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StrictInt,
    StrictStr,
    field_validator,
    model_validator,
)


def _utc(value: datetime) -> datetime:
    return value.astimezone(timezone.utc)


def _nonblank(value: str) -> str:
    if not value.strip():
        raise ValueError("Value must not be blank")
    return value


UtcDatetime = Annotated[AwareDatetime, AfterValidator(_utc)]
NonblankString = Annotated[StrictStr, AfterValidator(_nonblank)]


class AnalyticsModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class LogDimension(str, Enum):
    SOURCE = "source"
    EVENT_NAME = "event_name"
    SEVERITY = "severity"
    SESSION_ID = "session_id"
    TOOL_NAME = "tool_name"


class BucketWidth(str, Enum):
    MINUTE = "minute"
    HOUR = "hour"
    DAY = "day"


class InstanceScope(AnalyticsModel):
    kind: Literal["instance"]


class OwnersScope(AnalyticsModel):
    kind: Literal["owners"]
    owner_ids: Annotated[tuple[NonblankString, ...], Field(min_length=1)]

    @field_validator("owner_ids")
    @classmethod
    def unique_owners(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(set(value)) != len(value):
            raise ValueError("Owner IDs must be unique")
        return value


class TimeRange(AnalyticsModel):
    start: UtcDatetime
    end: UtcDatetime

    @model_validator(mode="after")
    def ordered_range(self) -> Self:
        if self.start >= self.end:
            raise ValueError("Start must precede end")
        return self


class DimensionFilter(AnalyticsModel):
    dimension: LogDimension
    values: Annotated[tuple[StrictStr, ...], Field(min_length=1)]

    @field_validator("values")
    @classmethod
    def unique_values(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(set(value)) != len(value):
            raise ValueError("Filter values must be unique")
        return value


class NoTimeBuckets(AnalyticsModel):
    kind: Literal["none"]


class FixedTimeBuckets(AnalyticsModel):
    kind: Literal["fixed"]
    width: BucketWidth


class PaginationQuery(AnalyticsModel):
    limit: Annotated[StrictInt, Field(ge=1, le=1000)]
    offset: Annotated[StrictInt, Field(ge=0, le=9007199254740991)]


class LogCountQuery(AnalyticsModel):
    scope: Annotated[InstanceScope | OwnersScope, Field(discriminator="kind")]
    time_range: TimeRange
    filters: tuple[DimensionFilter, ...]
    group_by: tuple[LogDimension, ...]
    bucketing: Annotated[NoTimeBuckets | FixedTimeBuckets, Field(discriminator="kind")]
    pagination: PaginationQuery

    @model_validator(mode="after")
    def unique_dimensions(self) -> Self:
        dimensions = tuple(item.dimension for item in self.filters)
        if len(set(dimensions)) != len(dimensions):
            raise ValueError("Filter dimensions must be unique")
        if len(set(self.group_by)) != len(self.group_by):
            raise ValueError("Grouping dimensions must be unique")
        return self


class MissingDimensionValue(AnalyticsModel):
    kind: Literal["missing"]


class PresentDimensionValue(AnalyticsModel):
    kind: Literal["present"]
    value: StrictStr


class DimensionGroup(AnalyticsModel):
    dimension: LogDimension
    value: Annotated[
        MissingDimensionValue | PresentDimensionValue, Field(discriminator="kind")
    ]


class Unbucketed(AnalyticsModel):
    kind: Literal["none"]


class TimeBucket(AnalyticsModel):
    kind: Literal["bucket"]
    start: UtcDatetime


class LogCountRow(AnalyticsModel):
    groups: tuple[DimensionGroup, ...]
    count: Annotated[StrictInt, Field(ge=0)]
    bucket: Annotated[Unbucketed | TimeBucket, Field(discriminator="kind")]


class LogCountResult(AnalyticsModel):
    rows: tuple[LogCountRow, ...]
    has_more: bool
