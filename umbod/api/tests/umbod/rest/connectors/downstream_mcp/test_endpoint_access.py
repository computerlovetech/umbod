import json

import pytest
from fastapi.testclient import TestClient

from tests.support.personal_oauth_metadata import InMemoryPersonalOAuthMetadataProvider
from tests.umbod.rest.connectors.downstream_mcp.personal_connections.test_personal_oauth_routes import (
    OAuthApi,
    oauth_api as oauth_api,
)
from umbod.core.connectors.downstream_mcp.endpoint_access import (
    AnonymousAccessRejected,
    AnonymousInitializationResult,
    CheckMcpEndpointAccess,
)
from umbod.core.connectors.downstream_mcp.personal_oauth_metadata import (
    DiscoveredPersonalOAuthMetadata,
)
from umbod.rest.connectors.downstream_mcp.endpoint_access import (
    get_anonymous_mcp_initialization,
)
from umbod.rest.connectors.downstream_mcp.personal_oauth_metadata import (
    get_metadata_provider,
)

from .test_personal_catalogue import client as client
from .test_personal_oauth_metadata import admin_app

URL = "/api/admin/connectors/mcp/check-access"
ENDPOINT = "https://resource.example/mcp"


class RejectedInitialization:
    def __init__(self) -> None:
        self.commands: list[CheckMcpEndpointAccess] = []

    async def initialize(
        self, command: CheckMcpEndpointAccess
    ) -> AnonymousInitializationResult:
        self.commands.append(command)
        return AnonymousAccessRejected(status_code=401)


@pytest.fixture
def initialization(client: TestClient) -> RejectedInitialization:
    probe = RejectedInitialization()
    metadata = InMemoryPersonalOAuthMetadataProvider(
        DiscoveredPersonalOAuthMetadata(
            endpoint_url=ENDPOINT,
            issuer_url="https://issuer.example",
            available_scopes=(),
            scope_source="unavailable",
            automatic_registration="unavailable",
            automatic_client={"kind": "unavailable"},
            token_endpoint_auth_methods=("none",),
        )
    )

    def provide_initialization() -> RejectedInitialization:
        return probe

    def provide_metadata() -> InMemoryPersonalOAuthMetadataProvider:
        return metadata

    app = admin_app(client)
    app.dependency_overrides[get_anonymous_mcp_initialization] = provide_initialization
    app.dependency_overrides[get_metadata_provider] = provide_metadata
    return probe


def test_check_access_returns_separate_evidence_without_registering_connector(
    client: TestClient, initialization: RejectedInitialization
) -> None:
    response = client.post(URL, json={"endpoint_url": ENDPOINT})

    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"
    assert response.json()["anonymous_initialization"] == {
        "kind": "anonymous_access_rejected",
        "status_code": 401,
    }
    assert (
        response.json()["oauth"]["metadata"]["issuer_url"] == "https://issuer.example"
    )
    assert response.json()["oauth"]["kind"] == "oauth_discovered"
    assert initialization.commands == [CheckMcpEndpointAccess(endpoint_url=ENDPOINT)]
    assert client.get("/api/admin/connectors/mcp").json() == {"connectors": []}


@pytest.mark.parametrize(
    ("body", "status"),
    [
        (b'{"endpoint_url":"invalid-private-input"}', 422),
        (b'{"endpoint_url":"https://resource.example/mcp","credential":"secret"}', 422),
        (b" " * 12289, 413),
    ],
)
def test_check_access_rejects_invalid_body_without_echoing_it(
    client: TestClient, initialization: RejectedInitialization, body: bytes, status: int
) -> None:
    response = client.post(
        URL, content=body, headers={"Content-Type": "application/json"}
    )

    assert response.status_code == status
    assert response.headers["Cache-Control"] == "no-store"
    assert response.json() == {"detail": {"code": "invalid_mcp_endpoint_access_check"}}
    assert initialization.commands == []


def test_check_access_is_admin_only(oauth_api: OAuthApi) -> None:
    body = {"endpoint_url": ENDPOINT}
    non_admin = {
        "X-Access": json.dumps(
            {"signature": "trusted", "claims": {"sub": "alice", "groups": ["team"]}}
        )
    }

    assert oauth_api.client.post(URL, json=body).status_code == 401
    assert oauth_api.client.post(URL, headers=non_admin, json=body).status_code == 403
    assert (
        oauth_api.client.post(
            URL,
            headers={**oauth_api.admin_headers, "Cookie": "session=fixture"},
            json=body,
        ).status_code
        == 403
    )
    personal_response = oauth_api.client.post(
        URL.replace("/admin/", "/me/"), headers={"X-Access": "alice"}, json=body
    )
    assert personal_response.status_code == 405
    assert "POST" not in personal_response.headers["Allow"]
