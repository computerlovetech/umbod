from uuid import UUID, uuid4

from umbod.core.persistence import AllFields, Database, Equals, InsertCommand, Query, ReadSession, TransactionMode, Unordered

from ..drafts import DraftReceipt
from .models import ManagedConnectorReceipt, PortableConnectorSubmission
from .ports import (
    ManagedSubmissionConflict,
    ManagedSubmissionLookupUnavailable,
    ManagedSubmissionMissing,
    ManagedSubmissionWriteUnconfirmed,
)
from .schema import DRAFT_ID, MANAGED_CONNECTOR_TABLE, ManagedConnectorRow


class DatabaseManagedConnectorStore:
    def __init__(self, database: Database) -> None:
        self._database = database

    async def find_submission(self, revision: DraftReceipt) -> ManagedConnectorReceipt | ManagedSubmissionMissing:
        try:
            async with self._database.read_session() as session:
                return await _find_submission(session, revision)
        except ManagedSubmissionConflict:
            raise
        except Exception:
            raise ManagedSubmissionLookupUnavailable() from None

    async def submit(self, submission: PortableConnectorSubmission) -> ManagedConnectorReceipt:
        try:
            async with self._database.session(mode=TransactionMode.SERIALIZED_WRITE) as session:
                existing = await _find_submission(session, submission.revision)
                if isinstance(existing, ManagedConnectorReceipt):
                    return existing
                receipt = ManagedConnectorReceipt(uuid4(), submission.revision.revision_id, "inactive")
                if not await session.insert(MANAGED_CONNECTOR_TABLE, InsertCommand(row=_new_row(submission, receipt))):
                    raise ManagedSubmissionWriteUnconfirmed()
                return receipt
        except (ManagedSubmissionConflict, ManagedSubmissionWriteUnconfirmed):
            raise
        except Exception:
            raise ManagedSubmissionWriteUnconfirmed() from None


async def _find_submission(
    session: ReadSession, revision: DraftReceipt,
) -> ManagedConnectorReceipt | ManagedSubmissionMissing:
    row = await session.find_one(
        MANAGED_CONNECTOR_TABLE, Query(Equals(DRAFT_ID, str(revision.draft_id)), AllFields(), Unordered()),
    )
    if row is None:
        return ManagedSubmissionMissing.NOT_SUBMITTED
    if row.revision_id != str(revision.revision_id):
        raise ManagedSubmissionConflict()
    if row.source_sha256 != revision.source_sha256 or row.status != "inactive":
        raise ValueError("Invalid managed submission record")
    return ManagedConnectorReceipt(UUID(row.connector_id), UUID(row.revision_id), "inactive")


def _new_row(submission: PortableConnectorSubmission, receipt: ManagedConnectorReceipt) -> ManagedConnectorRow:
    snapshot = submission.snapshot
    return ManagedConnectorRow(
        draft_id=str(submission.revision.draft_id), connector_id=str(receipt.connector_id),
        revision_id=str(receipt.revision_id), source_sha256=submission.revision.source_sha256,
        profile_id=submission.profile_id, status=receipt.status, declared_connector_id=snapshot.declared_connector_id,
        display_name=snapshot.display_name, description=snapshot.description,
        configuration_schema_json=snapshot.configuration_schema_json,
    )
