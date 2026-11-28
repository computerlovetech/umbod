from asyncio import Semaphore
from uuid import UUID

from umbod.core.callers import CallerContext

from ..drafts import DraftRevision, PortableConnectorDrafts
from .models import DraftValidationReport
from .ports import DraftSourceValidator, DraftValidationUnavailable


class PortableDraftValidation:
    def __init__(
        self, drafts: PortableConnectorDrafts, validator: DraftSourceValidator, max_concurrent_validations: int
    ) -> None:
        if max_concurrent_validations < 1:
            raise ValueError("At least one concurrent draft validation is required")
        self._drafts = drafts
        self._validator = validator
        self._slots = Semaphore(max_concurrent_validations)

    async def validate_revision(
        self, caller: CallerContext, draft_id: UUID, revision_id: UUID
    ) -> DraftValidationReport:
        revision = await self._drafts.read_revision(caller, draft_id, revision_id)
        return await self.validate_saved_revision(revision)

    async def validate_saved_revision(self, revision: DraftRevision) -> DraftValidationReport:
        if self._slots.locked():
            raise DraftValidationUnavailable("The draft validator is busy")
        async with self._slots:
            outcome = await self._validator.validate(revision.source)
        receipt = revision.receipt
        return DraftValidationReport(receipt.draft_id, receipt.revision_id, self._validator.profile_id, outcome)
