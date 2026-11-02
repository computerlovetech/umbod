from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, Field, StrictInt, model_validator

from umbod.core.telemetry.analytics import (
    DimensionFilter,
    FixedTimeBuckets,
    InstanceScope,
    LogCountQuery,
    LogDimension,
    NoTimeBuckets,
    TimeRange,
)


class LogCountRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    time_range: TimeRange
    filters: tuple[DimensionFilter, ...]
    group_by: tuple[LogDimension, ...]
    bucketing: Annotated[NoTimeBuckets | FixedTimeBuckets, Field(discriminator="kind")]
    max_groups: Annotated[StrictInt, Field(ge=1, le=1000)]

    def to_query(self) -> LogCountQuery:
        return LogCountQuery(
            scope=InstanceScope(kind="instance"),
            time_range=self.time_range,
            filters=self.filters,
            group_by=self.group_by,
            bucketing=self.bucketing,
            max_groups=self.max_groups,
        )

    @model_validator(mode="after")
    def validate_query(self) -> Self:
        self.to_query()
        return self
