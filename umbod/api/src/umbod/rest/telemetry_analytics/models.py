from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from umbod.core.telemetry.analytics import (
    DimensionFilter,
    FixedTimeBuckets,
    InstanceScope,
    LogCountQuery,
    LogDimension,
    NoTimeBuckets,
    PaginationQuery,
    TimeRange,
)


class LogCountRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    time_range: TimeRange
    filters: Annotated[tuple[DimensionFilter, ...], Field(max_length=len(LogDimension))]
    group_by: Annotated[tuple[LogDimension, ...], Field(max_length=len(LogDimension))]
    bucketing: Annotated[NoTimeBuckets | FixedTimeBuckets, Field(discriminator="kind")]
    pagination: PaginationQuery

    def to_query(self) -> LogCountQuery:
        return LogCountQuery(
            scope=InstanceScope(kind="instance"),
            time_range=self.time_range,
            filters=self.filters,
            group_by=self.group_by,
            bucketing=self.bucketing,
            pagination=self.pagination,
        )

    @model_validator(mode="after")
    def validate_query(self) -> Self:
        self.to_query()
        return self
