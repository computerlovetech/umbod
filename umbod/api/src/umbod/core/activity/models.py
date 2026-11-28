from typing import Annotated, Literal

from pydantic import ConfigDict, Field, NonNegativeInt

from umbod.proxies import Model
from umbod.core.telemetry.analytics.models import TimeRange, UtcDatetime
from umbod.core.telemetry.analytics.write_models import OwnedLog
from umbod.core.usage.models import UsageSummary, UsageWindowDays

HarnessSource = Literal['claude-code', 'claude-code-desktop', 'codex', 'codex_exec']
SessionId = Annotated[str, Field(min_length=1, max_length=1024)]
SearchTerm = Annotated[str, Field(max_length=128)]
SessionLimit = Annotated[int, Field(ge=1, le=100)]


class ActivityModel(Model):
    model_config = ConfigDict(frozen=True, extra='forbid')


class ActivityPeriod(ActivityModel):
    days: UsageWindowDays
    as_of: UtcDatetime
    window: TimeRange


class HarnessOutcomes(ActivityModel):
    success: NonNegativeInt
    failure: NonNegativeInt
    unknown: NonNegativeInt


class RankedTool(ActivityModel):
    tool_name: Annotated[str, Field(min_length=1)]
    count: Annotated[int, Field(gt=0)]


TopTools = Annotated[tuple[RankedTool, ...], Field(max_length=5)]


class HarnessSummary(ActivityModel):
    outcomes: HarnessOutcomes
    top_tools: TopTools
    skill_activations: NonNegativeInt


class HarnessAvailable(ActivityModel):
    status: Literal['available']
    summary: HarnessSummary


class McpAvailable(ActivityModel):
    status: Literal['available']
    summary: UsageSummary


class SourceUnavailable(ActivityModel):
    status: Literal['unavailable']


class ActivityOverview(ActivityModel):
    period: ActivityPeriod
    harness: Annotated[HarnessAvailable | SourceUnavailable, Field(discriminator='status')]
    mcp: Annotated[McpAvailable | SourceUnavailable, Field(discriminator='status')]


class SessionKey(ActivityModel):
    source: HarnessSource
    session_id: SessionId


class SessionPosition(ActivityModel):
    key: SessionKey
    last_seen_at: UtcDatetime


class SessionSummary(ActivityModel):
    key: SessionKey
    first_seen_at: UtcDatetime
    last_seen_at: UtcDatetime
    outcomes: HarnessOutcomes

    def position(self) -> SessionPosition:
        return SessionPosition(key=self.key, last_seen_at=self.last_seen_at)


class FirstPage(ActivityModel):
    kind: Literal['first']


class AfterSession(ActivityModel):
    kind: Literal['after']
    position: SessionPosition


PageStart = Annotated[FirstPage | AfterSession, Field(discriminator='kind')]


class SessionListQuery(ActivityModel):
    owner: OwnedLog
    window: TimeRange
    search: SearchTerm
    limit: SessionLimit
    start: PageStart


class SessionSlice(ActivityModel):
    sessions: tuple[SessionSummary, ...]
    has_more: bool


class SessionDetailQuery(ActivityModel):
    owner: OwnedLog
    key: SessionKey


class SessionReport(ActivityModel):
    session: SessionSummary
    top_tools: TopTools
    failed_tools: Annotated[tuple[RankedTool, ...], Field(max_length=100)]
    has_more_failed_tools: bool
    skill_activations: NonNegativeInt


class MissingSession(ActivityModel):
    kind: Literal['missing']


class CursorToken(ActivityModel):
    value: Annotated[str, Field(min_length=1, max_length=16384)]


class SessionCursor(ActivityModel):
    version: Literal[1]
    owner_binding: Annotated[str, Field(pattern=r'^[0-9a-f]{64}$')]
    days: UsageWindowDays
    as_of: UtcDatetime
    search: SearchTerm
    position: SessionPosition


class MoreSessions(ActivityModel):
    kind: Literal['more']
    cursor: str


class NoMoreSessions(ActivityModel):
    kind: Literal['end']


class SessionPage(ActivityModel):
    period: ActivityPeriod
    sessions: tuple[SessionSummary, ...]
    page: Annotated[MoreSessions | NoMoreSessions, Field(discriminator='kind')]
