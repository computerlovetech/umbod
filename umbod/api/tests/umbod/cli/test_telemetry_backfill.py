import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

import pytest
from typer.testing import CliRunner

from umbod.cli import telemetry
from umbod.cli.main import app
from umbod.config import AppConfig
from umbod.core.telemetry.analytics.backfill import (
    BackfillSelectionLimitExceeded,
    BackfillWindow,
    LogArchiveBackfillStore,
    ReplayBatch,
    ReplaySummary,
)

_WINDOW = ("--from", "2026-02-01T13:00:00+01:00", "--to", "2026-02-01T13:01:00+01:00")
_RECEIVED_AT = datetime(2026, 2, 1, 12, tzinfo=timezone.utc)
_PRIVATE_DETAIL = "private raw payload or credential"


class InMemoryBackfillStore:
    def __init__(self) -> None:
        self.batch_ids: tuple[int, ...] = (42, 43, 44)
        self.selections: list[BackfillWindow] = []
        self.previews: list[int] = []
        self.applies: list[int] = []
        self.runs: list[tuple[AppConfig, bool]] = []
        self.closed: bool = False
        self.failing_batch_id: int | None = None

    @asynccontextmanager
    async def open(self, config: AppConfig, *, apply: bool) -> AsyncIterator[LogArchiveBackfillStore]:
        self.runs.append((config, apply))
        try:
            yield self
        finally:
            self.closed = True

    async def select(self, window: BackfillWindow) -> tuple[ReplayBatch, ...]:
        self.selections.append(window)
        if len(self.batch_ids) > window.limit:
            raise BackfillSelectionLimitExceeded(_PRIVATE_DETAIL)
        return tuple(ReplayBatch(batch_id=batch_id) for batch_id in self.batch_ids)

    async def preview(self, batch: ReplayBatch) -> ReplaySummary:
        self.previews.append(batch.batch_id)
        return self._summarize(batch)

    async def apply(self, batch: ReplayBatch) -> ReplaySummary:
        self.applies.append(batch.batch_id)
        return self._summarize(batch)

    def _summarize(self, batch: ReplayBatch) -> ReplaySummary:
        if batch.batch_id == self.failing_batch_id:
            raise RuntimeError(_PRIVATE_DETAIL)
        return ReplaySummary(batch_id=batch.batch_id, received_at=_RECEIVED_AT, record_count=5)


@pytest.fixture
def backfill_store(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> InMemoryBackfillStore:
    for name in tuple(os.environ):
        if name.upper().startswith("UMBOD_"):
            monkeypatch.delenv(name)
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text(
        "UMBOD_ROOT_SECRET=backfill-test-root\n"
        "UMBOD_TELEMETRY_ANALYTICS_ENABLED=true\n"
    )
    store = InMemoryBackfillStore()
    monkeypatch.setattr(telemetry, "create_log_archive_backfill", store.open)
    return store


def test_backfill_single_batch_previews_with_server_configuration(
    backfill_store: InMemoryBackfillStore,
) -> None:
    result = CliRunner().invoke(app, ["telemetry", "backfill", "--batch-id", "42"])

    assert result.exit_code == 0, result.output
    [(config, apply)] = backfill_store.runs
    assert config.telemetry_analytics.enabled
    assert not apply
    assert backfill_store.previews == [42]
    assert backfill_store.applies == []
    assert backfill_store.selections == []
    assert backfill_store.closed
    assert "Preview 1/1: batch_id=42" in result.stderr
    assert "batch_id=42 received_at=2026-02-01T12:00:00+00:00 record_count=5" in result.stdout


@pytest.mark.parametrize("limit_options,limit", [((), 100), (("--limit", "3"), 3)])
def test_backfill_applies_selected_batches_with_bounded_utc_window(
    backfill_store: InMemoryBackfillStore, limit_options: tuple[str, ...], limit: int,
) -> None:
    result = CliRunner().invoke(app, ["telemetry", "backfill", *_WINDOW, *limit_options, "--apply"])

    assert result.exit_code == 0, result.output
    [(_, apply)] = backfill_store.runs
    assert apply
    assert backfill_store.applies == [42, 43, 44]
    assert backfill_store.previews == []
    [window] = backfill_store.selections
    assert window.start.isoformat() == "2026-02-01T12:00:00+00:00"
    assert window.end.isoformat() == "2026-02-01T12:01:00+00:00"
    assert window.limit == limit


def test_backfill_empty_window_completes_without_processing_batches(
    backfill_store: InMemoryBackfillStore,
) -> None:
    backfill_store.batch_ids = ()

    result = CliRunner().invoke(app, ["telemetry", "backfill", *_WINDOW])

    assert result.exit_code == 0, result.output
    assert "Preview complete: 0 batch(es)." in result.stdout
    assert backfill_store.previews == []


def test_backfill_limit_overflow_fails_before_any_apply_and_closes_runtime(
    backfill_store: InMemoryBackfillStore,
) -> None:
    result = CliRunner().invoke(app, ["telemetry", "backfill", *_WINDOW, "--limit", "2", "--apply"])

    assert result.exit_code == 1
    assert "Selection exceeds the batch limit" in result.stderr
    assert _PRIVATE_DETAIL not in result.output
    assert backfill_store.applies == []
    assert backfill_store.closed


def test_backfill_stops_after_first_failure_reports_progress_and_closes_runtime(
    backfill_store: InMemoryBackfillStore,
) -> None:
    backfill_store.failing_batch_id = 43

    result = CliRunner().invoke(app, ["telemetry", "backfill", *_WINDOW, "--apply"])

    assert result.exit_code == 1
    assert "Apply stopped at batch_id=43: 1 of 3 batch(es) completed." in result.stderr
    assert _PRIVATE_DETAIL not in result.output
    assert backfill_store.applies == [42, 43]
    assert backfill_store.closed


def test_backfill_refuses_invalid_server_configuration_before_opening_archive(
    backfill_store: InMemoryBackfillStore, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("UMBOD_REST_PORT", _PRIVATE_DETAIL)

    result = CliRunner().invoke(app, ["telemetry", "backfill", "--batch-id", "42"])

    assert result.exit_code == 1
    assert "Check the server configuration" in result.stderr
    assert _PRIVATE_DETAIL not in result.output
    assert backfill_store.runs == []


@pytest.mark.parametrize(
    "options",
    [
        (),
        ("--batch-id", "42", *_WINDOW),
        ("--batch-id", "42", "--limit", "1"),
        ("--batch-id", "0"),
        ("--batch-id", _PRIVATE_DETAIL),
        _WINDOW[:2],
        _WINDOW[2:],
        ("--from", "2026-02-01T12:00:00", *_WINDOW[2:]),
        ("--from", _WINDOW[3], *_WINDOW[2:]),
        (*_WINDOW, "--limit", "0"),
    ],
)
def test_backfill_invalid_selection_is_rejected_without_opening_archive(
    backfill_store: InMemoryBackfillStore, options: tuple[str, ...],
) -> None:
    result = CliRunner().invoke(app, ["telemetry", "backfill", *options])

    assert result.exit_code == 2
    assert "Error" in result.stderr
    assert _PRIVATE_DETAIL not in result.output
    assert backfill_store.runs == []
