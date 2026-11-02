from uuid import uuid4

import pytest

from .conftest import FilesystemHttp
from .test_http_contract import BASE

REVISION = {"If-Match": '"1"'}


@pytest.mark.parametrize("principal_type", ["user", "group"])
def test_access_rejects_obsolete_user_or_group_grants(
    filesystem_http: FilesystemHttp, principal_type: str,
) -> None:
    response = filesystem_http.client.put(
        f"{BASE}/nodes/{uuid4()}/access", headers=REVISION, json={"grants": [{
            "principal": {"type": principal_type, "issuer": "issuer", "id": "recipient"},
            "permissions": ["discover", "read"],
        }]},
    )
    assert response.status_code == 422


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

