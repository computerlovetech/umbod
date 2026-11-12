import pytest

from umbod.core.filesystem import AccessGrant, NodeMetadata, Permission, Principal, PrincipalType, WrongNodeKind
from umbod.core.filesystem.authorization import PermissionDenied, VerifiedIdentityResolver
from umbod.core.filesystem.content import ContentDownload, ContentService, ExternalDownloadInstructions
from umbod.core.filesystem.namespace import ROOT_ID
from tests.support.filesystem.downloads import DirectDownloadContent

from tests.umbod.core.filesystem.test_authorized_content import (
    ContentContext, caller, content_context as content_context, metadata, stream,
)
from tests.umbod.core.filesystem.test_verified_identity import snapshot


@pytest.mark.asyncio
async def test_external_delivery_authorizes_and_returns_instructions_without_reading_bytes(content_context: ContentContext) -> None:
    driver = DirectDownloadContent()
    service = ContentService(VerifiedIdentityResolver(), content_context.transactions, driver, 6)
    node = await service.upload(caller(), ROOT_ID, "notes.md", NodeMetadata(content_type="text/markdown", attributes={}), stream(b"# Hi"))
    download = await service.prepare_download(caller(), node.id)
    assert isinstance(download, ExternalDownloadInstructions)
    assert download.url == "https://storage.example.test/object?signature=secret"
    assert len(driver.download_requests) == 1
    request = driver.download_requests[0]
    assert request.name == "notes.md"
    assert request.metadata.content_type == "text/markdown"
    assert request.content.size == 4
    assert driver.read_keys == []


@pytest.mark.asyncio
@pytest.mark.parametrize("permissions", [set(), {Permission.DISCOVER}, {Permission.READ}])
async def test_external_delivery_requires_discover_and_read_before_signing(
    content_context: ContentContext, permissions: set[Permission],
) -> None:
    driver = DirectDownloadContent()
    service = ContentService(VerifiedIdentityResolver(), content_context.transactions, driver, 6)
    node = await service.upload(caller(), ROOT_ID, "private", metadata(), stream(b"secret"))
    await content_context.policies.add_grant(AccessGrant(
        node_id=node.id, principal=Principal(type=PrincipalType.USER, issuer="issuer", id="bob"),
        permissions=permissions, recursive=False,
    ))
    with pytest.raises(PermissionDenied):
        await service.prepare_download(snapshot("bob", "issuer", ()), node.id)
    assert driver.download_requests == []
    assert driver.read_keys == []


@pytest.mark.asyncio
async def test_external_backend_keeps_embedded_reads_and_unstored_empty_files_streamed(content_context: ContentContext) -> None:
    driver = DirectDownloadContent()
    service = ContentService(VerifiedIdentityResolver(), content_context.transactions, driver, 6)
    node = await service.upload(caller(), ROOT_ID, "embedded", metadata(), stream(b"bytes"))
    embedded = await service.open_download(caller(), node.id)
    assert b"".join([part async for part in embedded.data]) == b"bytes"
    empty = await content_context.creation.create_file(caller(), ROOT_ID, "empty", metadata())
    prepared = await service.prepare_download(caller(), empty.id)
    assert isinstance(prepared, ContentDownload)
    assert prepared.size == 0
    assert b"".join([part async for part in prepared.data]) == b""
    assert driver.download_requests == []


@pytest.mark.asyncio
async def test_nonexternal_backend_retains_streamed_delivery(content_context: ContentContext) -> None:
    node = await content_context.service.upload(caller(), ROOT_ID, "local", metadata(), stream(b"local"))
    download = await content_context.service.prepare_download(caller(), node.id)
    assert isinstance(download, ContentDownload)
    assert b"".join([part async for part in download.data]) == b"local"


@pytest.mark.asyncio
async def test_directory_is_rejected_before_signing(content_context: ContentContext) -> None:
    driver = DirectDownloadContent()
    service = ContentService(VerifiedIdentityResolver(), content_context.transactions, driver, 6)
    node = await content_context.creation.create_directory(caller(), ROOT_ID, "directory", metadata())
    with pytest.raises(WrongNodeKind):
        await service.prepare_download(caller(), node.id)
    assert driver.download_requests == []


@pytest.mark.parametrize("url", [
    "javascript:alert(1)", "/relative", "https://user:pass@storage.test/object",
    "https://storage.test/object#fragment", "https://storage.test/\r\nheader", "//storage.test/object",
])
def test_external_download_instructions_reject_unsafe_urls(url: str) -> None:
    with pytest.raises(ValueError):
        ExternalDownloadInstructions(url=url)


def test_external_download_instruction_representation_hides_signed_url() -> None:
    download = ExternalDownloadInstructions(url="https://storage.test/object?signature=private")
    assert "signature" not in repr(download)
    assert "private" not in repr(download)
