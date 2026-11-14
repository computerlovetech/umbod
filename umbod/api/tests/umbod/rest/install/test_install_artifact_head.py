import pytest
from fastapi.testclient import TestClient

@pytest.mark.parametrize("harness", ["codex", "claude-code"])
@pytest.mark.parametrize("artifact", ["package.zip", "package.sha256", "marketplace.txt", "endpoint.txt"])
def test_head_returns_get_headers_without_body(client: TestClient, harness: str, artifact: str) -> None:
    path = f"/api/install/v1/{harness}/{artifact}"
    response = client.head(path)
    expected = client.get(path)
    assert response.status_code == expected.status_code == 200
    assert response.content == b""
    for header in (
        "content-type", "content-length", "content-disposition", "cache-control", "x-content-type-options",
    ):
        assert response.headers[header] == expected.headers[header]
