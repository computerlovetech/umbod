from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import UUID

from umbod.core.persistence import (
    AllFields,
    AllOf,
    Database,
    DatabaseSession,
    Equals,
    InsertCommand,
    Query,
    ReadSession,
    TransactionMode,
    Unordered,
    UpsertCommand,
)

from .errors import DraftHeadChanged, DraftReadUnavailable, DraftRevisionNotFound, DraftWriteUnconfirmed
from .models import DraftAuthor, DraftReceipt, DraftRevision
from .schema import (
    AUTHOR_ISSUER,
    AUTHOR_SUBJECT,
    DRAFT_ID,
    DRAFT_TABLE,
    REVISION_DRAFT_ID,
    REVISION_ID,
    REVISION_TABLE,
    DraftKey,
    DraftRow,
    RevisionRow,
)


class DatabaseDraftStore:
    def __init__(self, database: Database) -> None:
        self._database = database

    async def create(self, author: DraftAuthor, revision: DraftRevision) -> None:
        draft = _draft_head(author, revision.receipt)
        async with self._write() as session:
            if not await session.insert(DRAFT_TABLE, InsertCommand(row=draft)):
                raise DraftWriteUnconfirmed("Could not confirm the draft write")
            await _insert_revision(session, revision)

    async def append(self, author: DraftAuthor, expected_revision_id: UUID, revision: DraftRevision) -> None:
        async with self._write() as session:
            current = await _owned_draft(session, author, revision.receipt.draft_id)
            if current.head_revision_id != str(expected_revision_id):
                raise DraftHeadChanged("The draft head has changed")
            await _insert_revision(session, revision)
            await session.upsert(
                DRAFT_TABLE,
                UpsertCommand(key=DraftKey(draft_id=current.draft_id), row=_draft_head(author, revision.receipt)),
            )

    async def read(self, author: DraftAuthor, draft_id: UUID, revision_id: UUID) -> DraftRevision:
        try:
            async with self._database.read_session() as session:
                await _owned_draft(session, author, draft_id)
                row = await session.find_one(
                    REVISION_TABLE,
                    Query(
                        AllOf((Equals(REVISION_DRAFT_ID, str(draft_id)), Equals(REVISION_ID, str(revision_id)))),
                        AllFields(),
                        Unordered(),
                    ),
                )
                if row is None:
                    raise DraftRevisionNotFound("Draft or revision not found")
                return DraftRevision(DraftReceipt(draft_id, revision_id, row.source_sha256), row.source)
        except DraftRevisionNotFound:
            raise
        except Exception:
            raise DraftReadUnavailable("Could not read the draft revision") from None

    @asynccontextmanager
    async def _write(self) -> AsyncIterator[DatabaseSession]:
        try:
            async with self._database.session(mode=TransactionMode.SERIALIZED_WRITE) as session:
                yield session
        except (DraftHeadChanged, DraftRevisionNotFound, DraftWriteUnconfirmed):
            raise
        except Exception:
            raise DraftWriteUnconfirmed("Could not confirm the draft write") from None


async def _owned_draft(session: ReadSession, author: DraftAuthor, draft_id: UUID) -> DraftRow:
    row = await session.find_one(
        DRAFT_TABLE,
        Query(
            AllOf((
                Equals(DRAFT_ID, str(draft_id)),
                Equals(AUTHOR_ISSUER, author.issuer),
                Equals(AUTHOR_SUBJECT, author.subject),
            )),
            AllFields(),
            Unordered(),
        ),
    )
    if row is None:
        raise DraftRevisionNotFound("Draft or revision not found")
    return row


def _draft_head(author: DraftAuthor, receipt: DraftReceipt) -> DraftRow:
    return DraftRow(
        draft_id=str(receipt.draft_id),
        issuer=author.issuer,
        subject=author.subject,
        head_revision_id=str(receipt.revision_id),
    )


async def _insert_revision(session: DatabaseSession, revision: DraftRevision) -> None:
    receipt = revision.receipt
    row = RevisionRow(
        draft_id=str(receipt.draft_id),
        revision_id=str(receipt.revision_id),
        source=revision.source,
        source_sha256=receipt.source_sha256,
    )
    if not await session.insert(REVISION_TABLE, InsertCommand(row=row)):
        raise DraftWriteUnconfirmed("Could not confirm the draft write")
