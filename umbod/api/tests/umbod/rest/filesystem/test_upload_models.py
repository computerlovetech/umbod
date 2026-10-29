import pytest
from pydantic import ValidationError

from umbod.rest.filesystem.models import SameOriginAuthorization, SingleUploadTransfer

from .conftest import FilesystemHttp
from .test_content import begin_typed_upload, upload_path as upload_path


@pytest.mark.parametrize("content_type", ["", "\r\n", "text/plain\r\nX-Injected: yes", " text/plain", "text/plain ", "text", "text/", "text/😀", "text/plain\x00"])
def test_begin_rejects_content_types_that_cannot_form_usable_headers(
    filesystem_http: FilesystemHttp, upload_path: str, content_type: str,
) -> None:
    assert begin_typed_upload(filesystem_http.client, upload_path, "invalid", b"x", content_type).status_code == 422
    assert filesystem_http.client.get(upload_path.removesuffix("/uploads") + "/children").json() == {"nodes": []}


@pytest.mark.parametrize("headers", [
    {"Content-Type": "application/octet-stream", "X-Receiver-Checksum": "checksum", "x-provider-option": "custom"},
    {"Content-Type": "text/plain; charset=utf-8"},
])
def test_single_transfer_supports_valid_custom_receiver_headers(headers: dict[str, str]) -> None:
    transfer = SingleUploadTransfer(
        url="/uploads/content", headers=headers, authorization=SameOriginAuthorization(),
    )
    assert transfer.headers == headers


@pytest.mark.parametrize("headers", [
    {"": "value"}, {"Invalid Header": "value"}, {"X-Injected\r\n": "value"}, {"😀": "value"},
    {"X-Receiver": "value\r\nInjected: yes"}, {"X-Receiver": "value\n"}, {"X-Receiver": "\x00"},
])
def test_single_transfer_rejects_invalid_header_names_and_values(headers: dict[str, str]) -> None:
    with pytest.raises(ValidationError):
        SingleUploadTransfer(url="/uploads/content", headers=headers, authorization=SameOriginAuthorization())
