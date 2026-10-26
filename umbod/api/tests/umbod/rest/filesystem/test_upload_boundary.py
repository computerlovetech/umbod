from uuid import uuid4

import pytest

from .conftest import FilesystemHttp
from .test_http_contract import BASE


@pytest.mark.parametrize("body", [b"{", b"\xff"])
def test_legacy_file_creation_rejects_malformed_json_without_server_error(
    filesystem_http: FilesystemHttp, body: bytes,
) -> None:
    response = filesystem_http.client.post(
        f"{BASE}/nodes/{uuid4()}/files", content=body,
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 422
    assert response.headers["cache-control"] == "no-store"
