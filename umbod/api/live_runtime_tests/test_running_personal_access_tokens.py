import os
from collections.abc import Iterator
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from pydantic import SecretStr

from conftest import RuntimeEndpoints
from umbod.core.personal_access_tokens import PersonalAccessTokenMetadata
from umbod.core.personal_access_tokens.access import (
    TELEMETRY_INGEST_SCOPE,
    TELEMETRY_TOKEN_AUDIENCE,
)

TOKEN_API_PATH = "/api/me/personal-access-tokens"


def test_running_setup_advertises_configured_collector_not_forwarded_origin(
    runtime_endpoints: RuntimeEndpoints,
) -> None:
    bearer = os.environ.get("UMBOD_TEST_MEMBER_BEARER_TOKEN", runtime_endpoints.bearer_token)
    with httpx.Client(timeout=30) as client:
        response = client.get(
            runtime_endpoints.api_base_url + "/api/me/telemetry/setup",
            headers={
                "Authorization": "Bearer " + bearer,
                "Forwarded": "proto=https;host=forged.runtime.invalid",
                "X-Forwarded-Host": "forged.runtime.invalid",
                "X-Forwarded-Proto": "https",
            },
        )
        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-store"
        assert response.json() == {
            "status": "available",
            "logs_endpoint": "https://collector.runtime.invalid/otlp/v1/logs",
        }
        if "UMBOD_TEST_MEMBER_BEARER_TOKEN" in os.environ:
            denied = client.get(runtime_endpoints.api_base_url + "/api/me/telemetry/setup")
            assert denied.status_code == 401
            assert denied.headers["cache-control"] == "no-store"


@pytest.mark.skipif(
    "UMBOD_TEST_MEMBER_BEARER_TOKEN" in os.environ,
    reason="Requires the local development runtime stage",
)
@pytest.mark.parametrize("signal", ["logs", "metrics", "traces"])
def test_running_local_user_token_revocation_is_immediate(
    runtime_endpoints: RuntimeEndpoints,
    personal_token: tuple[PersonalAccessTokenMetadata, SecretStr],
    signal: str,
) -> None:
    metadata, token = personal_token
    assert metadata.owner.issuer == "urn:umbod:local"
    user_headers = {"Authorization": "Bearer " + runtime_endpoints.bearer_token}
    token_headers = {"Authorization": "Bearer " + token.get_secret_value()}
    with httpx.Client(timeout=30) as client:
        listed = client.get(
            runtime_endpoints.api_base_url + TOKEN_API_PATH, headers=user_headers
        )
        assert listed.status_code == 200
        assert any(item["token_id"] == metadata.token_id for item in listed.json())
        assert token.get_secret_value() not in listed.text
        assert "digest" not in listed.text
        endpoint = runtime_endpoints.otlp_base_url + "/v1/" + signal
        assert client.post(endpoint, json={}, headers=token_headers).status_code == 200
        revoked = client.delete(
            runtime_endpoints.api_base_url + TOKEN_API_PATH + "/" + metadata.token_id,
            headers=user_headers,
        )
        assert revoked.status_code == 204
        listed = client.get(
            runtime_endpoints.api_base_url + TOKEN_API_PATH, headers=user_headers
        )
        assert listed.status_code == 200
        assert all(item["token_id"] != metadata.token_id for item in listed.json())
        repeated = client.delete(
            runtime_endpoints.api_base_url + TOKEN_API_PATH + "/" + metadata.token_id,
            headers=user_headers,
        )
        assert repeated.status_code == 404
        assert client.post(endpoint, json={}, headers=token_headers).status_code == 401

verified_user_stage = pytest.mark.skipif(
    "UMBOD_TEST_MEMBER_BEARER_TOKEN" not in os.environ,
    reason="Requires the verified-user runtime stage",
)


@pytest.fixture
def personal_token(
    runtime_endpoints: RuntimeEndpoints,
) -> Iterator[tuple[PersonalAccessTokenMetadata, SecretStr]]:
    headers = {"Authorization": "Bearer " + runtime_endpoints.bearer_token}
    with httpx.Client(
        base_url=runtime_endpoints.api_base_url,
        headers=headers,
        timeout=30,
    ) as client:
        response = client.post(
            TOKEN_API_PATH,
            json={
                "permissions": {"telemetry": "write"},
                "name": "Codex runtime verification",
                "expires_at": (
                    datetime.now(timezone.utc) + timedelta(hours=1)
                ).isoformat(),
            },
        )
        assert response.status_code == 201
        assert response.headers["cache-control"] == "no-store"
        data = response.json()
        metadata = PersonalAccessTokenMetadata.model_validate(data["metadata"])
        token = SecretStr(data["token"])
        try:
            yield metadata, token
        finally:
            revoked = client.delete(TOKEN_API_PATH + "/" + metadata.token_id)
            assert revoked.status_code in (204, 404)


@verified_user_stage
@pytest.mark.parametrize("signal", ["logs", "metrics", "traces"])
def test_running_personal_token_allows_only_telemetry_ingestion(
    runtime_endpoints: RuntimeEndpoints,
    personal_token: tuple[PersonalAccessTokenMetadata, SecretStr],
    signal: str,
) -> None:
    metadata, token = personal_token
    assert metadata.audience == TELEMETRY_TOKEN_AUDIENCE
    assert metadata.scopes == (TELEMETRY_INGEST_SCOPE,)
    headers = {"Authorization": "Bearer " + token.get_secret_value()}
    with httpx.Client(headers=headers, timeout=30) as client:
        collected = client.post(
            runtime_endpoints.otlp_base_url + "/v1/" + signal, json={}
        )
        assert collected.status_code == 200
        for path in (
            "/api/me/profile",
            TOKEN_API_PATH,
            "/api/admin/overview",
        ):
            denied = client.get(runtime_endpoints.api_base_url + path)
            assert denied.status_code == 401
        analytics = client.post(
            runtime_endpoints.api_base_url + "/api/admin/telemetry/log-counts",
            json={},
        )
        assert analytics.status_code == 401
        mcp = client.post(
            runtime_endpoints.mcp_url,
            headers={"Accept": "application/json, text/event-stream"},
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
        )
        assert mcp.status_code == 401


@verified_user_stage
def test_running_owner_revocation_is_visible_to_collector_across_api_processes(
    runtime_endpoints: RuntimeEndpoints,
    personal_token: tuple[PersonalAccessTokenMetadata, SecretStr],
) -> None:
    metadata, token = personal_token
    user_headers = {"Authorization": "Bearer " + runtime_endpoints.bearer_token}
    token_headers = {"Authorization": "Bearer " + token.get_secret_value()}
    with httpx.Client(timeout=30) as client:
        listed = client.get(
            runtime_endpoints.api_base_url + TOKEN_API_PATH,
            headers=user_headers,
        )
        assert listed.status_code == 200
        assert any(item["token_id"] == metadata.token_id for item in listed.json())
        assert token.get_secret_value() not in listed.text
        assert "digest" not in listed.text
        foreign_headers = {
            "Authorization": "Bearer " + os.environ["UMBOD_TEST_MEMBER_BEARER_TOKEN"],
        }
        foreign = client.delete(
            runtime_endpoints.api_base_url + TOKEN_API_PATH + "/" + metadata.token_id,
            headers=foreign_headers,
        )
        assert foreign.status_code == 404
        collected = client.post(
            runtime_endpoints.otlp_base_url + "/v1/logs",
            json={},
            headers=token_headers,
        )
        assert collected.status_code == 200
        revoked = client.delete(
            os.environ["UMBOD_TEST_API_B_BASE_URL"]
            + TOKEN_API_PATH
            + "/"
            + metadata.token_id,
            headers=user_headers,
        )
        assert revoked.status_code == 204
        listed = client.get(
            runtime_endpoints.api_base_url + TOKEN_API_PATH, headers=user_headers
        )
        assert listed.status_code == 200
        assert all(item["token_id"] != metadata.token_id for item in listed.json())
        repeated = client.delete(
            runtime_endpoints.api_base_url + TOKEN_API_PATH + "/" + metadata.token_id,
            headers=user_headers,
        )
        assert repeated.status_code == 404
        rejected = client.post(
            runtime_endpoints.otlp_base_url + "/v1/logs",
            json={},
            headers=token_headers,
        )
        assert rejected.status_code == 401
