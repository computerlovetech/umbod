from asyncio import Lock
from collections.abc import AsyncIterator
from dataclasses import dataclass
from uuid import UUID

import pytest
import pytest_asyncio

from tests.persistence_runtime import prepared_inmemory_runtime
from umbod.core.connectors.portable.drafts import (
    DatabaseDraftStore,
    DraftHeadChanged,
    DraftRevisionNotFound,
    PortableConnectorDrafts,
)
from umbod.core.connectors.portable.drafts.models import DraftAuthor, DraftRevision


@dataclass
class _Draft:
    author: DraftAuthor
    head: UUID
    revisions: dict[UUID, DraftRevision]


class _InMemoryDraftStore:
    def __init__(self) -> None:
        self._drafts: dict[UUID, _Draft] = {}
        self._lock = Lock()

    async def create(self, author: DraftAuthor, revision: DraftRevision) -> None:
        async with self._lock:
            receipt = revision.receipt
            if receipt.draft_id in self._drafts:
                raise RuntimeError("Duplicate draft ID")
            self._drafts[receipt.draft_id] = _Draft(author, receipt.revision_id, {receipt.revision_id: revision})

    async def append(self, author: DraftAuthor, expected_revision_id: UUID, revision: DraftRevision) -> None:
        async with self._lock:
            receipt = revision.receipt
            draft = self._owned_draft(author, receipt.draft_id)
            if draft.head != expected_revision_id:
                raise DraftHeadChanged("The draft head has changed")
            if receipt.revision_id in draft.revisions:
                raise RuntimeError("Duplicate revision ID")
            draft.revisions[receipt.revision_id] = revision
            draft.head = receipt.revision_id

    async def read(self, author: DraftAuthor, draft_id: UUID, revision_id: UUID) -> DraftRevision:
        async with self._lock:
            revisions = self._owned_draft(author, draft_id).revisions
            if revision_id not in revisions:
                raise DraftRevisionNotFound("Draft or revision not found")
            return revisions[revision_id]

    def _owned_draft(self, author: DraftAuthor, draft_id: UUID) -> _Draft:
        draft = self._drafts.get(draft_id)
        if draft is None or draft.author != author:
            raise DraftRevisionNotFound("Draft or revision not found")
        return draft


@pytest_asyncio.fixture(params=["contract-fake", "database-memory"])
async def drafts(request: pytest.FixtureRequest) -> AsyncIterator[PortableConnectorDrafts]:
    if request.param == "contract-fake":
        yield PortableConnectorDrafts(_InMemoryDraftStore())
        return
    runtime = await prepared_inmemory_runtime()
    try:
        yield PortableConnectorDrafts(DatabaseDraftStore(runtime.database))
    finally:
        await runtime.shutdown()
