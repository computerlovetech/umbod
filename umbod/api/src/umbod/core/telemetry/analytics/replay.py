from collections.abc import Callable
from typing import Annotated, Protocol

from pydantic import Field, StrictInt

from .models import AnalyticsModel, UtcDatetime
from .write_models import ArchivedLogWriteBatch, LogArchiveSource, LogWriteBatch


class ReplayBatch(AnalyticsModel):
    batch_id: Annotated[StrictInt, Field(gt=0, le=2**63 - 1)]


class ReplaySummary(ReplayBatch):
    received_at: UtcDatetime
    record_count: Annotated[StrictInt, Field(gt=0)]


class ReplayArchiveUnavailable(Exception):
    pass


class ReplayNormalizationFailed(Exception):
    pass


ReplayNormalizer = Callable[[LogArchiveSource], LogWriteBatch]
ReplayProjection = Callable[[LogArchiveSource], ArchivedLogWriteBatch]


class ReplayArchiveStore(Protocol):
    async def read(self, batch: ReplayBatch) -> LogArchiveSource: ...

    async def replace(self, batch: ReplayBatch, project: ReplayProjection) -> ReplaySummary: ...


class LogArchiveReplay:
    def __init__(self, store: ReplayArchiveStore, normalizer: ReplayNormalizer) -> None:
        self._store = store
        self._normalizer = normalizer

    async def preview(self, batch: ReplayBatch) -> ReplaySummary:
        source = await self._store.read(batch)
        return replay_summary(batch, self._project(source))

    async def apply(self, batch: ReplayBatch) -> ReplaySummary:
        return await self._store.replace(batch, self._project)

    def _project(self, source: LogArchiveSource) -> ArchivedLogWriteBatch:
        try:
            projected = self._normalizer(source)
            return ArchivedLogWriteBatch.model_validate(
                source.model_dump() | {"records": projected.model_dump()["records"]}
            )
        except Exception:
            pass
        raise ReplayNormalizationFailed("Archived log normalization failed")


def replay_summary(batch: ReplayBatch, projection: ArchivedLogWriteBatch) -> ReplaySummary:
    return ReplaySummary(
        batch_id=batch.batch_id,
        received_at=projection.received_at,
        record_count=len(projection.records),
    )
