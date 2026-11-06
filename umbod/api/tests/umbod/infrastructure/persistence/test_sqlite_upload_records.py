from datetime import datetime, timezone
from pathlib import Path
from typing import Union
from uuid import UUID

import pytest

from umbod.core.filesystem import ContentRef, NodeKind, NodeMetadata, Principal, PrincipalType
from umbod.core.filesystem.browsing import NodeSummary
from umbod.core.filesystem.namespace import ROOT_ID
from umbod.core.filesystem.stores.uploads import UPLOAD_ID, UPLOAD_TABLE, UploadKey, UploadRecord
from umbod.core.filesystem.uploads.models import (
    CompletedUpload, NoDelegatedTransfer, NoExpectedChecksum, PendingUpload,
    UnavailableReceipt, UploadedContent, UploadSession,
)
from umbod.core.persistence import AllFields, Equals, InsertCommand, Query, TransactionMode, Unordered, UpsertCommand
from tests.persistence_runtime import prepared_sqlite_runtime


@pytest.mark.asyncio
@pytest.mark.parametrize("progress", [
    pytest.param(PendingUpload(status="pending"), id="pending"),
    pytest.param(UploadedContent(
        status="uploaded", content=ContentRef(key="a" * 32, size=3),
        receipt=UnavailableReceipt(kind="unavailable"),
    ), id="uploaded"),
    pytest.param(CompletedUpload(
        status="completed",
        node=NodeSummary(
            id=UUID(int=2), parent_id=ROOT_ID, name="Résumé.txt", kind=NodeKind.FILE,
            metadata=NodeMetadata(content_type="text/plain", attributes={"label": "résumé"}),
            created_at=datetime(2026, 1, 1, 12, 30, 1, 123456, tzinfo=timezone.utc),
            updated_at=datetime(2026, 1, 1, 12, 31, 2, 654321, tzinfo=timezone.utc), revision=2,
        ),
        receipt=UnavailableReceipt(kind="unavailable"),
    ), id="completed"),
])
async def test_sqlite_upload_progress_updates_survive_runtime_recreation(
    tmp_path: Path, progress: Union[PendingUpload, UploadedContent, CompletedUpload],
) -> None:
    path = tmp_path / "uploads.sqlite"
    upload = UploadSession(
        id=UUID(int=1), owner=Principal(type=PrincipalType.USER, issuer="issuer", id="alice"),
        parent_id=ROOT_ID, name="Résumé.txt",
        metadata=NodeMetadata(content_type="text/plain", attributes={"label": "résumé"}),
        size_bytes=3, expires_at=datetime(2026, 1, 1, 13, 30, 1, 123456, tzinfo=timezone.utc),
        expected_checksum=NoExpectedChecksum(kind="unchecked"),
        delegated_transfer=NoDelegatedTransfer(kind="none"), progress=progress,
    )
    record = UploadRecord(upload_id=str(upload.id), payload=upload)
    initial = UploadRecord(upload_id=str(upload.id), payload=upload.model_copy(update={
        "name": "before-update", "progress": PendingUpload(status="pending"),
    }))
    runtime = await prepared_sqlite_runtime(path)
    try:
        async with runtime.database.session(mode=TransactionMode.SERIALIZED_WRITE) as session:
            assert await session.insert(UPLOAD_TABLE, InsertCommand(row=initial))
            await session.upsert(UPLOAD_TABLE, UpsertCommand(key=UploadKey(upload_id=record.upload_id), row=record))
    finally:
        await runtime.shutdown()
    reopened = await prepared_sqlite_runtime(path)
    try:
        async with reopened.database.read_session() as session:
            restored = await session.find_one(
                UPLOAD_TABLE, Query(Equals(UPLOAD_ID, record.upload_id), AllFields(), Unordered()),
            )
        assert restored == record
        assert restored is not None
        assert type(restored.payload.progress) is type(progress)
    finally:
        await reopened.shutdown()
