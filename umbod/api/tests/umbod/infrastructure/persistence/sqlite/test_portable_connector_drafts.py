import sqlite3
from asyncio import gather
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, closing
from pathlib import Path

import pytest

from tests.persistence_runtime import prepared_sqlite_runtime
from umbod.core.callers import AuthenticationProvenance, CallerContext, DeclaredIssuer, SubjectIdentity
from umbod.core.connectors.portable.drafts import (
    DatabaseDraftStore,
    DraftHeadChanged,
    DraftReceipt,
    DraftWriteUnconfirmed,
    PortableConnectorDrafts,
)

pytestmark = pytest.mark.asyncio

_AUTHOR = CallerContext(
    authentication=AuthenticationProvenance.UPSTREAM_VERIFIED,
    subject=SubjectIdentity(issuer=DeclaredIssuer(value="https://accounts.example"), subject="author"),
)


@asynccontextmanager
async def _drafts(database_path: Path) -> AsyncIterator[PortableConnectorDrafts]:
    runtime = await prepared_sqlite_runtime(database_path)
    try:
        yield PortableConnectorDrafts(DatabaseDraftStore(runtime.database))
    finally:
        await runtime.shutdown()


async def test_sqlite_restart_preserves_exact_draft_source_and_earlier_revisions(tmp_path: Path) -> None:
    database_path = tmp_path / "drafts.sqlite3"
    original = "  invalid syntax ???\r\n# æ\r\n"
    async with _drafts(database_path) as drafts:
        first = await drafts.create(_AUTHOR, original)
        second = await drafts.save_revision(_AUTHOR, first.draft_id, first.revision_id, "new source")

    async with _drafts(database_path) as drafts:
        first_revision = await drafts.read_revision(_AUTHOR, first.draft_id, first.revision_id)
        second_revision = await drafts.read_revision(_AUTHOR, second.draft_id, second.revision_id)
        assert (first_revision.receipt, first_revision.source) == (first, original)
        assert (second_revision.receipt, second_revision.source) == (second, "new source")
        with pytest.raises(DraftHeadChanged):
            await drafts.save_revision(_AUTHOR, first.draft_id, first.revision_id, "stale write")


async def test_independent_sqlite_connections_cannot_both_append_to_same_head(tmp_path: Path) -> None:
    database_path = tmp_path / "drafts.sqlite3"
    async with _drafts(database_path) as left, _drafts(database_path) as right:
        first = await left.create(_AUTHOR, "first")
        results = await gather(
            left.save_revision(_AUTHOR, first.draft_id, first.revision_id, "left"),
            right.save_revision(_AUTHOR, first.draft_id, first.revision_id, "right"),
            return_exceptions=True,
        )
        winners = [result for result in results if isinstance(result, DraftReceipt)]

        assert len(winners) == 1
        assert sum(isinstance(result, DraftHeadChanged) for result in results) == 1
        winner = await left.read_revision(_AUTHOR, first.draft_id, winners[0].revision_id)
        assert winner.source in {"left", "right"}


async def test_sqlite_failed_head_update_rolls_back_new_revision(tmp_path: Path) -> None:
    database_path = tmp_path / "drafts.sqlite3"
    async with _drafts(database_path) as drafts:
        first = await drafts.create(_AUTHOR, "original")
        with closing(sqlite3.connect(database_path)) as connection, connection:
            connection.execute(
                "CREATE TRIGGER reject_draft_head_update BEFORE UPDATE ON portable_connector_drafts "
                "BEGIN SELECT RAISE(ABORT, 'private storage diagnostic'); END"
            )

        with pytest.raises(DraftWriteUnconfirmed, match="^Could not confirm the draft write$"):
            await drafts.save_revision(_AUTHOR, first.draft_id, first.revision_id, "replacement")

        with closing(sqlite3.connect(database_path)) as connection, connection:
            revision_ids = connection.execute("SELECT revision_id FROM portable_connector_revisions").fetchall()
            assert revision_ids == [(str(first.revision_id),)]
            connection.execute("DROP TRIGGER reject_draft_head_update")
        confirmed = await drafts.save_revision(_AUTHOR, first.draft_id, first.revision_id, "replacement")
        assert (await drafts.read_revision(_AUTHOR, first.draft_id, confirmed.revision_id)).source == "replacement"
