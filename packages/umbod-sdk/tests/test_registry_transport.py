from io import BytesIO
from urllib.error import HTTPError, URLError
from urllib.request import Request

import pytest

from umbod_sdk.connector_checks.compatibility import ReleaseMetadataError
from umbod_sdk.connector_checks.registry_transport import (
    HttpRegistryTransport,
    RegistryRequest,
    RegistryTransport,
    _RegistryRedirectHandler,
)


class StubOpener:
    def __init__(self, body: bytes) -> None:
        self.body = body
        self.requests: list[Request] = []

    def open(self, request: Request, timeout: int) -> BytesIO:
        assert timeout == 15
        self.requests.append(request)
        return BytesIO(self.body)


def test_transport_bounds_response_and_sends_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    opener = StubOpener(b'{"schemaVersion": 2}')
    monkeypatch.setattr("umbod_sdk.connector_checks.registry_transport.build_opener", lambda handler: opener)
    transport: RegistryTransport = HttpRegistryTransport()
    response = transport.get(RegistryRequest(url="https://ghcr.io/v2/image/manifests/1.0.0", token="secret", accept="application/json"))
    assert response.content == opener.body
    assert opener.requests[0].get_header("Authorization") == "Bearer secret"


def test_transport_rejects_oversized_metadata(monkeypatch: pytest.MonkeyPatch) -> None:
    opener = StubOpener(b"x" * (4 * 1024 * 1024 + 1))
    monkeypatch.setattr("umbod_sdk.connector_checks.registry_transport.build_opener", lambda handler: opener)
    transport: RegistryTransport = HttpRegistryTransport()
    with pytest.raises(ReleaseMetadataError, match="response size"):
        transport.get(RegistryRequest(url="https://ghcr.io/token", token="", accept="application/json"))


@pytest.mark.parametrize("error", [HTTPError("https://ghcr.io/token?secret", 404, "secret", {}, None), HTTPError("https://ghcr.io", 403, "secret", {}, None), URLError("secret")])
def test_transport_failures_do_not_expose_tokens(monkeypatch: pytest.MonkeyPatch, error: Exception) -> None:
    class FailingOpener:
        def open(self, request: Request, timeout: int) -> BytesIO:
            raise error

    monkeypatch.setattr("umbod_sdk.connector_checks.registry_transport.build_opener", lambda handler: FailingOpener())
    transport: RegistryTransport = HttpRegistryTransport()
    with pytest.raises(ReleaseMetadataError) as captured:
        transport.get(RegistryRequest(url="https://ghcr.io/token", token="secret", accept="application/json"))
    assert "secret" not in str(captured.value)


def test_blob_redirect_strips_authorization() -> None:
    original = Request("https://ghcr.io/v2/image/blobs/sha256:abc", headers={"Authorization": "Bearer secret", "Accept": "application/json"})
    redirected = _RegistryRedirectHandler().redirect_request(original, object(), 307, "", {}, "https://pkg-containers.githubusercontent.com/blob")
    assert redirected.get_header("Authorization") is None


@pytest.mark.parametrize("url", ["http://ghcr.io/blob", "https://untrusted.example/blob", "https://ghcr.io:444/blob", "https://user@ghcr.io/blob"])
def test_unsafe_registry_redirect_is_refused(url: str) -> None:
    with pytest.raises(ReleaseMetadataError, match="unsupported location"):
        _RegistryRedirectHandler().redirect_request(Request("https://ghcr.io/token"), object(), 302, "", {}, url)
