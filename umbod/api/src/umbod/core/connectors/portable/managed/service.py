from asyncio import CancelledError, Future, get_running_loop, shield
from collections.abc import Callable
from uuid import UUID

from umbod.core.callers import CallerContext

from ..draft_validation import DraftValidationUnavailable, PortableDraftValidation
from ..draft_validation.models import ValidatedSource
from ..drafts import DraftReceipt, DraftRevision, PortableConnectorDrafts
from .configuration_schema import inactive_connector_snapshot
from .models import ManagedConnectorReceipt, PortableConnectorSubmission
from .ports import ManagedConnectorStore, ManagedSubmissionWriteUnconfirmed


class ManagedSubmissionInvalidRevision(Exception):
    pass


class PortableConnectorSubmit:
    def __init__(
        self, drafts: PortableConnectorDrafts, validation: Callable[[], PortableDraftValidation], store: ManagedConnectorStore,
    ) -> None:
        self._drafts = drafts
        self._validation = validation
        self._store = store
        self._pending: dict[DraftReceipt, Future[ManagedConnectorReceipt]] = {}

    async def submit(self, caller: CallerContext, draft_id: UUID, revision_id: UUID) -> ManagedConnectorReceipt:
        revision = await self._drafts.read_revision(caller, draft_id, revision_id)
        receipt = revision.receipt
        pending = self._pending.get(receipt)
        if pending is not None:
            return await shield(pending)
        existing = await self._store.find_submission(receipt)
        if isinstance(existing, ManagedConnectorReceipt):
            return existing
        pending = self._pending.get(receipt)
        if pending is not None:
            return await shield(pending)
        if self._pending:
            raise DraftValidationUnavailable("A portable connector submission is in progress")
        return await self._complete_submission(revision)

    async def _complete_submission(self, revision: DraftRevision) -> ManagedConnectorReceipt:
        pending: Future[ManagedConnectorReceipt] = get_running_loop().create_future()
        self._pending[revision.receipt] = pending
        try:
            result = await self._validate_and_store(revision)
            pending.set_result(result)
            return result
        except CancelledError:
            pending.set_exception(ManagedSubmissionWriteUnconfirmed())
            raise
        except Exception as error:
            pending.set_exception(error)
            raise
        finally:
            del self._pending[revision.receipt]
            if pending.done():
                pending.exception()

    async def _validate_and_store(self, revision: DraftRevision) -> ManagedConnectorReceipt:
        report = await self._validation().validate_saved_revision(revision)
        if report.outcome.status == "invalid":
            raise ManagedSubmissionInvalidRevision()
        if report.outcome.status != "valid" or not isinstance(report.outcome, ValidatedSource):
            raise DraftValidationUnavailable("Could not confirm offline validation for submission")
        snapshot = inactive_connector_snapshot(report.outcome.manifest)
        return await self._store.submit(PortableConnectorSubmission(revision.receipt, report.profile_id, snapshot))
