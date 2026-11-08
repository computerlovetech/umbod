from datetime import datetime, timedelta, timezone
from typing import cast
from uuid import UUID

from umbod.core.filesystem import ContentDriver
from umbod.core.filesystem.stores.uploads import DatabaseUploadTransactions
from umbod.core.filesystem.uploads.models import ExternalTransfer
from umbod.rest.filesystem.deps import get_filesystem_content_driver
from tests.umbod.core.filesystem.test_external_uploads import MemoryExternalContent

from .conftest import FilesystemHttp
from .test_content import begin_upload, upload_path as upload_path


def test_external_rest_instructions_pending_verification_and_unavailable_completed_descriptor(
    filesystem_http: FilesystemHttp, upload_path: str,
) -> None:
    async def inspect_namespace() -> None:
        return None

    content = MemoryExternalContent(
        filesystem_http.client.portal.call(get_filesystem_content_driver, filesystem_http.factories), inspect_namespace,
    )

    def external_content() -> ContentDriver:
        return cast(ContentDriver, content)

    filesystem_http.app.dependency_overrides[get_filesystem_content_driver] = external_content
    client = filesystem_http.client
    begin = begin_upload(client, upload_path, "external", b"abc")
    assert begin.status_code == 201
    assert begin.headers["cache-control"] == "no-store"
    data = begin.json()
    assert data["transfer"]["authorization"] == {"type": "none"}
    assert data["transfer"]["url"].startswith("https://objects.example.test/")
    assert data["transfer"]["headers"] == {"Content-Type": "application/octet-stream", "If-None-Match": "*"}
    assert "signature" not in begin.headers["location"]
    assert client.put(begin.headers["location"] + "/content", content=b"abc").status_code == 409
    key = content.preparations[-1].transfer.storage_key
    content.objects[key] = (b"abc", "application/octet-stream")
    status = client.get(begin.headers["location"])
    assert status.headers["cache-control"] == "no-store"
    assert status.json()["status"] == "pending"
    completed = client.post(data["complete_url"])
    assert completed.status_code == 201
    assert client.post(data["complete_url"]).json()["id"] == completed.json()["id"]
    assert content.verifications == 1
    count = len(content.preparations)
    final = client.get(begin.headers["location"])
    assert final.json()["status"] == "completed"
    assert final.json()["transfer"] == {"type": "unavailable", "reason": "completed"}
    assert len(content.preparations) == count


def test_expired_external_transfer_can_be_inspected_and_completed_without_signing(
    filesystem_http: FilesystemHttp, upload_path: str,
) -> None:
    async def inspect_namespace() -> None:
        return None

    content = MemoryExternalContent(
        filesystem_http.client.portal.call(get_filesystem_content_driver, filesystem_http.factories), inspect_namespace,
    )

    def external_content() -> ContentDriver:
        return cast(ContentDriver, content)

    filesystem_http.app.dependency_overrides[get_filesystem_content_driver] = external_content
    client = filesystem_http.client
    begin = begin_upload(client, upload_path, "expired-transfer", b"abc")
    data = begin.json()
    content.objects[content.preparations[-1].transfer.storage_key] = (b"abc", "application/octet-stream")

    async def expire_transfer() -> None:
        async with DatabaseUploadTransactions(filesystem_http.factories.persistence_runtime.database).transaction() as transaction:
            upload = await transaction.uploads.get(UUID(data["id"]))
            assert upload is not None and isinstance(upload.delegated_transfer, ExternalTransfer)
            await transaction.uploads.save(upload.model_copy(update={
                "delegated_transfer": upload.delegated_transfer.model_copy(update={
                    "expires_at": datetime.now(timezone.utc) - timedelta(seconds=1),
                }),
            }))

    client.portal.call(expire_transfer)
    status = client.get(begin.headers["location"])
    assert status.status_code == 200
    assert status.json()["transfer"] == {"type": "unavailable", "reason": "expired"}
    assert len(content.preparations) == 1
    assert client.post(data["complete_url"]).status_code == 201
    assert len(content.preparations) == 1
