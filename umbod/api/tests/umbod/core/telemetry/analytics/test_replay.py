from datetime import datetime, timezone

import pytest

from umbod.core.telemetry.analytics import LogWriteBatch, UnownedLog
from umbod.core.telemetry.analytics.replay import (
    LogArchiveReplay,
    ReplayBatch,
    ReplayNormalizationFailed,
    ReplayProjection,
    ReplaySummary,
    replay_summary,
)
from umbod.core.telemetry.analytics.write_models import LogArchiveSource


class InMemoryReplayArchive:
    def __init__(self, source: LogArchiveSource) -> None:
        self._source = source
        self.record_count = 1

    async def read(self, batch: ReplayBatch) -> LogArchiveSource:
        return self._source

    async def replace(self, batch: ReplayBatch, project: ReplayProjection) -> ReplaySummary:
        projection = project(self._source)
        self.record_count = len(projection.records)
        return replay_summary(batch, projection)


@pytest.mark.asyncio
async def test_normalizer_failure_is_sanitized_and_leaves_projection() -> None:
    source = LogArchiveSource(
        raw_payload=b"private-value",
        encoding="protobuf",
        received_at=datetime(2026, 3, 1, tzinfo=timezone.utc),
        owner=UnownedLog(kind="unowned"),
    )
    store = InMemoryReplayArchive(source)

    def fail(archived: LogArchiveSource) -> LogWriteBatch:
        raise RuntimeError(archived.raw_payload.decode())

    replay = LogArchiveReplay(store, fail)
    with pytest.raises(ReplayNormalizationFailed, match="^Archived log normalization failed$") as failure:
        await replay.apply(ReplayBatch(batch_id=1))

    assert failure.value.__context__ is None
    assert store.record_count == 1
