from typing import Annotated, Protocol

from pydantic import Field, StrictInt

from .models import TimeRange
from .replay import ReplayBatch, ReplaySummary


class BackfillWindow(TimeRange):
    limit: Annotated[StrictInt, Field(ge=1, lt=2**63 - 1)]


class BackfillSelectionLimitExceeded(Exception):
    pass


class LogArchiveBackfillStore(Protocol):
    async def select(self, window: BackfillWindow) -> tuple[ReplayBatch, ...]: ...

    async def preview(self, batch: ReplayBatch) -> ReplaySummary: ...

    async def apply(self, batch: ReplayBatch) -> ReplaySummary: ...
