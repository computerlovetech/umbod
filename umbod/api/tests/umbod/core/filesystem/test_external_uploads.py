import asyncio
import hashlib
from collections.abc import Awaitable, Callable
from datetime import timedelta
from uuid import uuid4

import pytest

from umbod.core.filesystem import ByteStream, ContentDriver, ContentRef, StorageKey
from umbod.core.filesystem.authorization import PermissionDenied, VerifiedIdentityResolver
from umbod.core.filesystem.content import UploadTooLarge
from umbod.core.filesystem.deletion import DeletionService
from umbod.core.filesystem.namespace import ROOT_ID
from umbod.core.filesystem.stores.uploads import DatabaseUploadTransactions
from umbod.core.filesystem.uploads import UploadService
from umbod.core.filesystem.uploads.errors import UploadChecksumMismatch, UploadConflict, UploadExpired, UploadLengthMismatch, UploadMediaTypeMismatch
from umbod.core.filesystem.uploads.models import ExternalTransfer, ExternalTransferInstructions, ExternalTransferRequest, ExpectedChecksum, NoExpectedChecksum, UploadedContent, UploadSession, VerifiedReceipt
from umbod.core.persistence import PersistenceRuntime
from tests.umbod.core.filesystem.test_authorized_content import alice, caller, metadata, stream
from tests.umbod.core.filesystem.test_authorized_content import content_context as content_context
from tests.umbod.core.filesystem.test_upload_sessions import UploadContext, uploads as uploads
from tests.umbod.core.filesystem.test_verified_identity import snapshot


class MemoryExternalContent:
    def __init__(self, content: ContentDriver, before_verify: Callable[[], Awaitable[None]]) -> None:
        self.content = content
        self.before_verify = before_verify
        self.objects: dict[str, tuple[bytes, str]] = {}
        self.preparations: list[ExternalTransferRequest] = []
        self.verifications = 0

    @property
    def max_transfer_bytes(self) -> int:
        return 5 * 1024 ** 3

    async def put(self, data: ByteStream) -> ContentRef:
        return await self.content.put(data)

    async def get(self, key: StorageKey) -> ByteStream:
        if key in self.objects:
            yield self.objects[key][0]
        else:
            async for chunk in self.content.get(key):
                yield chunk

    async def prepare_transfer(self, request: ExternalTransferRequest) -> ExternalTransferInstructions:
        self.preparations.append(request)
        return ExternalTransferInstructions(
            url=f"https://objects.example.test/bucket/{request.transfer.storage_key}?signature=secret",
            headers={"Content-Type": request.content_type, "If-None-Match": "*"},
        )

    async def verify_transfer(self, request: ExternalTransferRequest) -> UploadedContent:
        self.verifications += 1
        await self.before_verify()
        if request.transfer.storage_key not in self.objects:
            raise UploadConflict()
        data, content_type = self.objects[request.transfer.storage_key]
        if len(data) != request.size_bytes:
            raise UploadLengthMismatch()
        if content_type != request.content_type:
            raise UploadMediaTypeMismatch()
        return UploadedContent(
            content=ContentRef(key=request.transfer.storage_key, size=len(data)),
            receipt=VerifiedReceipt(size_bytes=len(data), sha256=hashlib.sha256(data).hexdigest()),
        )


def external_service(
    uploads: UploadContext, runtime: PersistenceRuntime,
) -> tuple[UploadService, MemoryExternalContent]:
    async def inspect_namespace() -> None:
        await uploads.content.namespace.list_children(ROOT_ID)

    content = MemoryExternalContent(uploads.content.content, inspect_namespace)
    service = UploadService(
        VerifiedIdentityResolver(), DatabaseUploadTransactions(runtime.database), content,
        6, uploads.clock, timedelta(hours=1),
    )
    return service, content


@pytest.mark.asyncio
async def test_external_completion_reads_outside_transaction_and_persists_receipt(
    uploads: UploadContext, filesystem_runtime: PersistenceRuntime,
) -> None:
    service, content = external_service(uploads, filesystem_runtime)
    upload = await service.begin_transfer(caller(), ROOT_ID, "external", metadata(), 3, NoExpectedChecksum())
    assert isinstance(upload.delegated_transfer, ExternalTransfer)
    instructions = await service.transfer_instructions(upload)
    assert instructions.url.startswith("https://objects.example.test/")
    assert "secret" not in repr(instructions)
    assert "signature" not in upload.model_dump_json()
    content.objects[upload.delegated_transfer.storage_key] = (b"abc", "application/octet-stream")
    assert (await service.get(caller(), upload.id)).progress.status == "pending"
    assert await uploads.content.namespace.list_children(ROOT_ID) == []
    with pytest.raises(UploadConflict):
        await service.put(caller(), upload.id, "application/octet-stream", stream(b"abc"))
    with pytest.raises(PermissionDenied):
        await service.put_delegated(upload.id, "x" * 43, "application/octet-stream", stream(b"abc"))
    results = await asyncio.wait_for(asyncio.gather(*(service.complete_verified(caller(), upload.id) for _ in range(4))), 5)
    assert sum(result.created for result in results) == 1
    assert all(result.node.id == results[0].node.id for result in results)
    count = content.verifications
    uploads.clock.current += timedelta(days=1)
    assert (await service.complete_verified(caller(), upload.id)).receipt == results[0].receipt
    assert content.verifications == count
    assert results[0].receipt.sha256 == hashlib.sha256(b"abc").hexdigest()
    completed = await service.get(caller(), upload.id)
    assert (await service.transfer_instructions(completed)).reason == "completed"
    assert len(content.preparations) == 1
    await DeletionService(VerifiedIdentityResolver(), uploads.content.transactions).delete_file(
        caller(), results[0].node.id, expected_revision=results[0].node.revision,
    )
    with pytest.raises(PermissionDenied):
        await service.complete_verified(caller(), upload.id)
    assert content.verifications == count


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["missing", "short", "long", "type", "checksum"])
async def test_external_failure_leaves_session_pending_and_namespace_empty(
    uploads: UploadContext, filesystem_runtime: PersistenceRuntime, failure: str,
) -> None:
    service, content = external_service(uploads, filesystem_runtime)
    upload = await service.begin_transfer(
        caller(), ROOT_ID, "invalid", metadata(), 3, ExpectedChecksum(sha256=hashlib.sha256(b"abc").hexdigest()),
    )
    assert isinstance(upload.delegated_transfer, ExternalTransfer)
    errors = {"missing": UploadConflict, "short": UploadLengthMismatch, "long": UploadLengthMismatch,
              "type": UploadMediaTypeMismatch, "checksum": UploadChecksumMismatch}
    if failure != "missing":
        content.objects[upload.delegated_transfer.storage_key] = (
            {"short": b"ab", "long": b"abcd", "checksum": b"xyz"}.get(failure, b"abc"),
            "text/plain" if failure == "type" else "application/octet-stream",
        )
    with pytest.raises(errors[failure]):
        await service.complete_verified(caller(), upload.id)
    assert (await service.get(caller(), upload.id)).progress.status == "pending"
    assert await uploads.content.namespace.list_children(ROOT_ID) == []


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["foreign", "revoked", "expired"])
async def test_external_completion_checks_authorization_before_readback(
    uploads: UploadContext, filesystem_runtime: PersistenceRuntime, failure: str,
) -> None:
    service, content = external_service(uploads, filesystem_runtime)
    upload = await service.begin_transfer(caller(), ROOT_ID, "private", metadata(), 0, NoExpectedChecksum())
    identity = caller()
    if failure == "foreign":
        identity = snapshot("bob", "issuer", ())
    elif failure == "revoked":
        await uploads.content.policies.remove_grant(ROOT_ID, alice())
    else:
        uploads.clock.current += timedelta(hours=1)
    with pytest.raises(UploadExpired if failure == "expired" else PermissionDenied):
        await service.complete_verified(identity, upload.id)
    assert content.verifications == 0


@pytest.mark.asyncio
async def test_transfer_deadline_is_fixed_and_internal_upload_still_uses_content_driver(
    uploads: UploadContext, filesystem_runtime: PersistenceRuntime,
) -> None:
    service, content = external_service(uploads, filesystem_runtime)
    upload = await service.begin_transfer(caller(), ROOT_ID, "deadline", metadata(), 0, NoExpectedChecksum())
    await service.transfer_instructions(upload)
    uploads.clock.current += timedelta(minutes=10)
    await service.transfer_instructions(await service.get(caller(), upload.id))
    assert content.preparations[0].transfer.expires_at == content.preparations[1].transfer.expires_at
    uploads.clock.current += timedelta(minutes=5)
    assert (await service.transfer_instructions(await service.get(caller(), upload.id))).reason == "expired"
    internal = await service.begin(caller(), ROOT_ID, "inline", metadata(), 1)
    await service.put(caller(), internal.id, "application/octet-stream", stream(b"x"))
    assert (await service.complete_verified(caller(), internal.id)).created


@pytest.mark.asyncio
async def test_external_admission_rejects_unauthorized_invalid_and_oversize_before_signing(
    uploads: UploadContext, filesystem_runtime: PersistenceRuntime,
) -> None:
    service, content = external_service(uploads, filesystem_runtime)
    with pytest.raises(PermissionDenied):
        await service.begin_transfer(caller(), uuid4(), "file", metadata(), 0, NoExpectedChecksum())
    with pytest.raises(UploadTooLarge):
        await service.begin_transfer(caller(), ROOT_ID, "large", metadata(), 7, NoExpectedChecksum())
    assert not content.preparations


@pytest.mark.asyncio
async def test_external_and_legacy_session_payloads_roundtrip(
    uploads: UploadContext, filesystem_runtime: PersistenceRuntime,
) -> None:
    service, _ = external_service(uploads, filesystem_runtime)
    upload = await service.begin_transfer(caller(), ROOT_ID, "serialization", metadata(), 0, NoExpectedChecksum())
    assert UploadSession.model_validate_json(upload.model_dump_json()) == upload
    legacy = upload.model_dump(mode="json")
    del legacy["delegated_transfer"]
    del legacy["expected_checksum"]
    assert UploadSession.model_validate(legacy).delegated_transfer.kind == "none"
