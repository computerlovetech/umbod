import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import httpx
import pytest
from pydantic import SecretStr

from conftest import RuntimeEndpoints


_TOKENS = "/api/admin/tokens/agents"
_GROUPS = "/api/admin/groups"
_PROTOCOL = "2025-11-25"
_INITIALIZE: dict[str, object] = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": _PROTOCOL,
        "capabilities": {},
        "clientInfo": {"name": "kind-agent-token-test", "version": "1"},
    },
}
_LIST_TOOLS: dict[str, object] = {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": "Bearer " + token}


def _mcp_headers() -> dict[str, str]:
    return {
        "Accept": "application/json, text/event-stream",
        "MCP-Protocol-Version": _PROTOCOL,
    }


def _open_session(
    client: httpx.Client, endpoint: str, token: SecretStr
) -> dict[str, str]:
    headers = _mcp_headers() | _bearer(token.get_secret_value())
    initialized = client.post(endpoint, headers=headers, json=_INITIALIZE)
    assert initialized.status_code == 200
    headers["Mcp-Session-Id"] = initialized.headers["Mcp-Session-Id"]
    ready = client.post(
        endpoint,
        headers=headers,
        json={
            "jsonrpc": "2.0",
            "method": "notifications/initialized",
        },
    )
    assert ready.status_code == 202
    assert client.post(endpoint, headers=headers, json=_LIST_TOOLS).status_code == 200
    return headers


@pytest.mark.skipif(
    "UMBOD_TEST_MEMBER_BEARER_TOKEN" not in os.environ,
    reason="Requires the runner's signed OIDC stage",
)
def test_rest_agent_token_rotation_and_revocation_reach_public_mcp_workers(
    runtime_endpoints: RuntimeEndpoints,
) -> None:
    group_id = "agent-test-" + uuid4().hex
    primary_api = runtime_endpoints.api_base_url
    secondary_api = os.environ["UMBOD_TEST_API_B_BASE_URL"]
    primary_mcp, secondary_mcp = (
        runtime_endpoints.mcp_url,
        os.environ["UMBOD_TEST_MCP_B_URL"],
    )
    admin = _bearer(runtime_endpoints.bearer_token)
    with httpx.Client(timeout=30, trust_env=False) as client:
        assert (
            client.post(
                primary_api + _GROUPS, headers=admin, json={"group_id": group_id}
            ).status_code
            == 204
        )
        try:
            created = client.post(
                primary_api + _TOKENS,
                headers=admin,
                json={
                    "display_name": "Kind agent",
                    "group_id": group_id,
                    "expires_at": (
                        datetime.now(timezone.utc) + timedelta(hours=1)
                    ).isoformat(),
                },
            )
            assert created.status_code == 201
            assert created.headers["cache-control"] == "no-store"
            issued = created.json()
            token = SecretStr(issued["token"])
            agent_path = _TOKENS + "/" + issued["metadata"]["agent_id"]
            try:
                assert isinstance(issued["metadata"]["expires_at"], str)
                sessions = [
                    (endpoint, _open_session(client, endpoint, token))
                    for endpoint in (primary_mcp, secondary_mcp)
                ]
                agent = _bearer(token.get_secret_value())
                assert (
                    client.get(primary_api + _TOKENS, headers=agent).status_code == 401
                )
                assert (
                    client.post(
                        runtime_endpoints.admin_mcp_url,
                        headers=_mcp_headers() | agent,
                        json=_INITIALIZE,
                    ).status_code
                    == 401
                )
                assert (
                    client.post(
                        runtime_endpoints.otlp_base_url + "/v1/logs",
                        headers=agent,
                        json={},
                    ).status_code
                    == 401
                )
                for endpoint, session in sessions:
                    unauthenticated = _mcp_headers() | {
                        "Mcp-Session-Id": session["Mcp-Session-Id"]
                    }
                    assert (
                        client.post(
                            endpoint, headers=unauthenticated, json=_LIST_TOOLS
                        ).status_code
                        == 401
                    )

                rotation = client.post(
                    secondary_api + agent_path + "/rotate",
                    headers=admin,
                    json={"expires_at": None},
                )
                assert rotation.status_code == 200
                rotated = rotation.json()
                assert rotated["metadata"]["expires_at"] is None
                assert rotated["metadata"]["agent_id"] == issued["metadata"]["agent_id"]
                listed = client.get(primary_api + _TOKENS, headers=admin)
                assert listed.status_code == 200
                assert rotated["metadata"] in listed.json()
                assert (
                    rotated["metadata"]["credential_id"]
                    != issued["metadata"]["credential_id"]
                )
                for endpoint, session in sessions:
                    assert (
                        client.post(
                            endpoint, headers=session, json=_LIST_TOOLS
                        ).status_code
                        == 401
                    )
                replacement = SecretStr(rotated["token"])
                sessions = [
                    (endpoint, _open_session(client, endpoint, replacement))
                    for endpoint in (primary_mcp, secondary_mcp)
                ]

                assert (
                    client.delete(secondary_api + agent_path, headers=admin).status_code
                    == 204
                )
                for endpoint, session in sessions:
                    assert (
                        client.post(
                            endpoint, headers=session, json=_LIST_TOOLS
                        ).status_code
                        == 401
                    )
            finally:
                client.delete(secondary_api + agent_path, headers=admin)
        finally:
            client.delete(primary_api + _GROUPS + "/" + group_id, headers=admin)
