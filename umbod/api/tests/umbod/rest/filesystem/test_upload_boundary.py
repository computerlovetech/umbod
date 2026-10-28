from typing import NoReturn
from uuid import uuid4

import pytest
from starlette.requests import Request

from umbod.rest.authentication.deps import get_caller_context

from .conftest import FilesystemHttp
from .test_http_contract import BASE, BODY


@pytest.mark.parametrize("body", [b"{", b"\xff"])
def test_file_creation_rejects_malformed_json_without_server_error(
    filesystem_http: FilesystemHttp, body: bytes,
) -> None:
    response = filesystem_http.client.post(
        f"{BASE}/nodes/{uuid4()}/files", content=body,
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 415
    assert response.json()["detail"]["code"] == "filesystem_upload_media_type"
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize("parent", ["root", "missing"])
def test_json_file_creation_is_rejected_before_body_or_parent_authorization(
    filesystem_http: FilesystemHttp, monkeypatch: pytest.MonkeyPatch, parent: str,
) -> None:
    client = filesystem_http.client
    root_id = client.get(f"{BASE}/root").json()["id"]
    parent_id = root_id if parent == "root" else uuid4()

    async def forbid_read(self: Request) -> NoReturn:
        pytest.fail("Non-multipart body was read.")

    monkeypatch.setattr(Request, "body", forbid_read)
    response = client.post(f"{BASE}/nodes/{parent_id}/files", json=BODY)
    assert response.status_code == 415
    assert response.json()["detail"]["code"] == "filesystem_upload_media_type"
    assert response.headers["cache-control"] == "no-store"
    assert client.get(f"{BASE}/nodes/{root_id}/children").json() == {"nodes": []}


def test_non_multipart_file_creation_requires_authentication_and_verified_identity(
    filesystem_http: FilesystemHttp,
) -> None:
    client = filesystem_http.client
    path = f"{BASE}/nodes/{uuid4()}/files"
    anonymous = client.post(path, json=BODY, headers={"Authorization": ""})
    assert anonymous.status_code == 401
    del filesystem_http.app.dependency_overrides[get_caller_context]
    unverified = client.post(path, json=BODY)
    assert unverified.status_code == 403
    assert unverified.json()["detail"]["code"] == "filesystem_permission_denied"
