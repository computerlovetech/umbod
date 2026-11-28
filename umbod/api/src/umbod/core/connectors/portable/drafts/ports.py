from typing import Protocol
from uuid import UUID

from .models import DraftAuthor, DraftRevision


class DraftStore(Protocol):
    async def create(self, author: DraftAuthor, revision: DraftRevision) -> None: ...

    async def append(self, author: DraftAuthor, expected_revision_id: UUID, revision: DraftRevision) -> None: ...

    async def read(self, author: DraftAuthor, draft_id: UUID, revision_id: UUID) -> DraftRevision: ...
