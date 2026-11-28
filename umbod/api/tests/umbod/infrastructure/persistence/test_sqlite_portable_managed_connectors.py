from asyncio import gather
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

import pytest

from tests.persistence_runtime import prepared_sqlite_runtime
from umbod.core.connectors.portable.drafts import DraftReceipt
from umbod.core.connectors.portable.managed import DatabaseManagedConnectorStore, ManagedSubmissionConflict
from umbod.core.connectors.portable.managed.models import InactiveConnectorSnapshot, PortableConnectorSubmission
from umbod.core.connectors.portable.managed.ports import ManagedConnectorStore


@pytest.mark.asyncio
async def test_managed_submission_is_atomic_and_survives_runtime_reopen(tmp_path: Path) -> None:
    path = tmp_path / "portable.sqlite"
    submission = PortableConnectorSubmission(
        revision=DraftReceipt(uuid4(), uuid4(), "a" * 64),
        profile_id="validation-profile",
        snapshot=InactiveConnectorSnapshot(
            declared_connector_id="probe", display_name="Probe", description="Inactive probe",
            configuration_schema_json='{"additionalProperties":false,"properties":{},"type":"object"}',
        ),
    )
    competing_revision = replace(submission, revision=replace(submission.revision, revision_id=uuid4()))
    independent_draft = replace(submission, revision=replace(submission.revision, draft_id=uuid4(), revision_id=uuid4()))
    first_runtime = await prepared_sqlite_runtime(path)
    second_runtime = await prepared_sqlite_runtime(path)
    try:
        store: ManagedConnectorStore = DatabaseManagedConnectorStore(first_runtime.database)
        concurrent_store: ManagedConnectorStore = DatabaseManagedConnectorStore(second_runtime.database)
        first, repeated = await gather(store.submit(submission), concurrent_store.submit(submission))
        assert first == repeated
        assert first.status == "inactive"
        assert await store.find_submission(submission.revision) == first
        with pytest.raises(ManagedSubmissionConflict):
            await concurrent_store.submit(competing_revision)
        distinct = await concurrent_store.submit(independent_draft)
        assert distinct.connector_id != first.connector_id
    finally:
        await second_runtime.shutdown()
        await first_runtime.shutdown()

    reopened = await prepared_sqlite_runtime(path)
    try:
        store = DatabaseManagedConnectorStore(reopened.database)
        assert await store.find_submission(submission.revision) == first
        assert await store.find_submission(independent_draft.revision) == distinct
        with pytest.raises(ManagedSubmissionConflict):
            await store.find_submission(competing_revision.revision)
    finally:
        await reopened.shutdown()
