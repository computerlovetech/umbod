from datetime import date, timedelta
from enum import StrEnum
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, FiniteFloat, model_validator


OwnerId = Annotated[str, Field(pattern=r'^[0-9a-f]{64}$')]
UsageWindowDays = Literal[7, 30]


class UsageModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra='forbid')


class UsageOwner(UsageModel):
    kind: Literal['owned']
    owner_id: OwnerId


class UnavailableUsageOwner(UsageModel):
    kind: Literal['unavailable']


UsageOwnership = UsageOwner | UnavailableUsageOwner


class UsageKind(StrEnum):
    TOOL = 'tool'
    RESOURCE = 'resource'
    PROMPT = 'prompt'


class UsageOutcome(StrEnum):
    SUCCESS = 'success'
    FAILURE = 'failure'
    CANCELLED = 'cancelled'


class UsageRecord(UsageModel):
    event_id: UUID
    owner_id: OwnerId
    occurred_at_unix_nano: Annotated[int, Field(ge=0)]
    observed_at_unix_nano: Annotated[int, Field(ge=0)]
    kind: UsageKind
    outcome: UsageOutcome
    duration_ms: Annotated[FiniteFloat, Field(ge=0)]
    service_name: Annotated[str, Field(min_length=1, max_length=128)]
    trace_id: Annotated[str, Field(pattern=r'^(?:[0-9a-f]{32})?$')]
    span_id: Annotated[str, Field(pattern=r'^(?:[0-9a-f]{16})?$')]


class UsageBatch(UsageModel):
    records: Annotated[tuple[UsageRecord, ...], Field(min_length=1, max_length=1024)]


class OutcomeCounts(UsageModel):
    success: Annotated[int, Field(ge=0)]
    failure: Annotated[int, Field(ge=0)]
    cancelled: Annotated[int, Field(ge=0)]

    @property
    def total(self) -> int:
        return self.success + self.failure + self.cancelled


class UsageCounts(UsageModel):
    tool: OutcomeCounts
    resource: OutcomeCounts
    prompt: OutcomeCounts

    @property
    def total(self) -> int:
        return self.tool.total + self.resource.total + self.prompt.total


class UsageDay(UsageModel):
    date: date
    counts: UsageCounts


class UsageRange(UsageModel):
    start: date
    end: date
    timezone: Literal['UTC']

    @model_validator(mode='after')
    def valid_window(self) -> Self:
        if (self.end - self.start).days not in (7, 30):
            raise ValueError('Usage windows must contain seven or thirty UTC days')
        return self


class OwnedUsageQuery(UsageModel):
    owner_id: OwnerId
    days: UsageWindowDays
    as_of: AwareDatetime


class UsageSummary(UsageModel):
    range: UsageRange
    as_of: AwareDatetime
    totals: UsageCounts
    daily: tuple[UsageDay, ...]

    @model_validator(mode='after')
    def consistent_counts(self) -> Self:
        expected_dates = tuple(
            self.range.start + timedelta(days=offset)
            for offset in range((self.range.end - self.range.start).days)
        )
        if tuple(day.date for day in self.daily) != expected_dates:
            raise ValueError('Usage days must exactly cover the requested window')
        for kind in UsageKind:
            for outcome in UsageOutcome:
                total = getattr(getattr(self.totals, kind.value), outcome.value)
                daily_total = sum(getattr(getattr(day.counts, kind.value), outcome.value) for day in self.daily)
                if total != daily_total:
                    raise ValueError('Usage totals must equal daily counts')
        return self
