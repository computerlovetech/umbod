from typing import NoReturn
from uuid import uuid4

import pytest
from starlette.requests import Request

from .conftest import FilesystemHttp
from .test_http_contract import BASE
from .test_planned import DETAIL, REVISION, forbid_database
from umbod.rest.filesystem.deps import get_filesystem_database


@pytest.mark.parametrize("rename", [False, True])
def test_patch_design_accepts_move_with_optional_rename(
    filesystem_http: FilesystemHttp, rename: bool,
) -> None:
    body = {"parent_id": str(uuid4())}
    if rename:
        body["name"] = "renamed"
    response = filesystem_http.client.patch(
        f"{BASE}/nodes/{uuid4()}", headers=REVISION, json=body,
    )
    assert response.status_code == 501
    assert response.json() == {"detail": DETAIL}


@pytest.mark.parametrize("principal_type", ["user", "group"])
def test_access_design_accepts_direct_user_or_group_grants(
    filesystem_http: FilesystemHttp, principal_type: str,
) -> None:
    response = filesystem_http.client.put(
        f"{BASE}/nodes/{uuid4()}/access", headers=REVISION, json={"grants": [{
            "principal": {"type": principal_type, "issuer": "issuer", "id": "recipient"},
            "permissions": ["discover", "read"],
        }]},
    )
    assert response.status_code == 501
    assert response.json() == {"detail": DETAIL}


@pytest.mark.parametrize("field,value", [("recursive", True), ("inherited", True), ("owner", "mallory")])
def test_access_design_rejects_uncontracted_authority_fields(
    filesystem_http: FilesystemHttp, field: str, value: object,
) -> None:
    response = filesystem_http.client.put(
        f"{BASE}/nodes/{uuid4()}/access", headers=REVISION, json={"grants": [{
            "principal": {"type": "user", "issuer": "issuer", "id": "recipient"},
            "permissions": ["read"], field: value,
        }]},
    )
    assert response.status_code == 422


def test_content_replacement_does_not_read_content_or_access_storage(
    filesystem_http: FilesystemHttp, monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def forbid_read(self: Request) -> NoReturn:
        pytest.fail("Replacement body was read.")

    monkeypatch.setattr(Request, "body", forbid_read)
    monkeypatch.setattr(Request, "form", forbid_read)
    filesystem_http.app.dependency_overrides[get_filesystem_database] = forbid_database
    response = filesystem_http.client.put(
        f"{BASE}/nodes/{uuid4()}/content", content=b"not stored",
        headers={**REVISION, "Content-Type": "application/octet-stream"},
    )
    assert response.status_code == 501
    assert response.json() == {"detail": DETAIL}
