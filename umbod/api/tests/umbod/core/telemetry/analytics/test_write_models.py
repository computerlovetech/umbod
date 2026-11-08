from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from umbod.core.telemetry.analytics import (
    AnalyticsLogRecord,
    LogWriteBatch,
    OwnedLog,
    UnownedLog,
)
from umbod.core.telemetry.normalization import UnavailableLogNormalization

EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


@pytest.mark.parametrize("owner_id", ["", " ", "\t", 1, None])
def test_owned_log_requires_nonblank_string(owner_id: object) -> None:
    with pytest.raises(ValidationError):
        OwnedLog(kind="owned", owner_id=owner_id)


@pytest.mark.parametrize("field", ["occurred_at", "owner", "dimensions", "normalization"])
def test_log_record_requires_explicit_fields(field: str) -> None:
    values = {"occurred_at": EPOCH, "owner": {"kind": "unowned"}, "dimensions": (), "normalization": {"kind": "unavailable", "reason": "legacy_or_unspecified"}}
    del values[field]
    with pytest.raises(ValidationError):
        AnalyticsLogRecord.model_validate(values)


def test_log_record_rejects_naive_time() -> None:
    with pytest.raises(ValidationError):
        AnalyticsLogRecord(
            normalization=UnavailableLogNormalization(kind="unavailable", reason="legacy_or_unspecified"),
            occurred_at=datetime(1970, 1, 1),
            owner=UnownedLog(kind="unowned"),
            dimensions=(),
        )


def test_write_batch_roundtrips_immutable_records() -> None:
    batch = LogWriteBatch(
        records=(
            AnalyticsLogRecord(
                normalization=UnavailableLogNormalization(kind="unavailable", reason="legacy_or_unspecified"),
                occurred_at=EPOCH,
                owner=UnownedLog(kind="unowned"),
                dimensions=(),
            ),
        )
    )
    assert LogWriteBatch.model_validate_json(batch.model_dump_json()) == batch
    with pytest.raises(ValidationError):
        batch.records = ()
