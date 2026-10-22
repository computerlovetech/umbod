import asyncio
import base64
import hashlib
import html
import re
import secrets
from contextlib import contextmanager
from collections.abc import Iterator
import json
import os
from pathlib import Path
import ssl
from typing import Any
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

import httpx
import pytest
from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport

from conftest import RuntimeEndpoints

ISSUER = "https://personal-runtime.kind.invalid"
PERMISSIONS = "/api/admin/mcp-permissions/groups/admin/permissions"


def checked(response: httpx.Response, status: int = 200) -> dict[str, Any]:
    assert response.status_code == status, f"Unexpected HTTP status {response.status_code}"
    return response.json() if response.content else {}


def contract(connector_id: str, name: str) -> dict[str, Any]:
    return {"identity": {"connector_id": connector_id, "downstream_name": name}, "title": "Approved public tool", "description": "Administrator approved public contract", "input_schema": {"additionalProperties": False, "properties": {"message": {"type": "string"}}, "required": ["message"], "type": "object"}, "output_schema_status": "present", "output_schema": {"additionalProperties": {"type": "string"}, "type": "object"}}


@contextmanager
def personal_clients(endpoints: RuntimeEndpoints) -> Iterator[tuple[httpx.Client, httpx.Client, httpx.Client, str]]:
    context = ssl.create_default_context(cafile=os.environ["UMBOD_TEST_PERSONAL_CA"])
    with httpx.Client(base_url=endpoints.api_base_url, headers={"Authorization": f"Bearer {endpoints.bearer_token}"}, timeout=90) as alice, httpx.Client(base_url=endpoints.api_base_url, headers={"Authorization": "Bearer " + os.environ["UMBOD_TEST_BEARER_TOKEN_B"]}, timeout=90) as bob, httpx.Client(base_url=os.environ["UMBOD_TEST_PERSONAL_URL"], verify=context, timeout=30, follow_redirects=False) as fixture:
        created = checked(alice.post("/api/admin/connectors/mcp/personal-oauth", json={"metadata": {"display_name": "Controlled personal runtime", "capability_description": "Controlled TLS interoperability", "public_path": "/mcp/proxies/runtime-" + uuid4().hex[:20]}, "configuration": {"endpoint_url": ISSUER + "/mcp", "oauth_configuration": {"requested_scopes": ["read"], "client": {"kind": "preconfigured_public", "issuer_url": ISSUER, "client_id": "kind-personal-client"}}}}), 201)
        connector_id = created["connector_id"]
        admin = f"/api/admin/connectors/mcp/{connector_id}"
        try:
            checked(alice.put(admin + "/publication"))
            grant(alice, connector_id, "enabled", connector=True)
            for client in (alice, bob):
                checked(client.put(f"/api/me/connectors/mcp/{connector_id}/enablement", json={"enabled": True}))
            yield alice, bob, fixture, connector_id
        finally:
            grant(alice, connector_id, "disabled")
            grant(alice, connector_id, "disabled", connector=True)
            checked(alice.delete(admin + "/publication"))
            checked(alice.delete(admin), 204)


def grant(client: httpx.Client, connector_id: str, status: str, connector: bool = False) -> None:
    body = {"connectors": [{"connector_id": connector_id, "permission_status": status}]} if connector else {"capabilities": [{"connector_id": connector_id, "capability_kind": "tool", "capability_key": name, "permission_status": status} for name in ("echo_owner", "exclusive_alice")]}
    checked(client.put(PERMISSIONS, json=body))


def authorize(client: httpx.Client, fixture: httpx.Client, connector_id: str, owner: str) -> None:
    personal = f"/api/me/connectors/mcp/{connector_id}"
    started = checked(client.post(personal + "/oauth/attempts", json={}), 201)
    authorization = urlsplit(started["authorization_url"])
    consent = fixture.get(authorization.path + "?" + authorization.query + "&owner=" + owner)
    assert consent.status_code == 302
    callback = urlsplit(consent.headers["location"])
    assert callback.hostname == "umbod-runtime.kind.invalid"
    response = client.get(callback.path + "?" + callback.query, follow_redirects=False)
    assert response.status_code in (200, 302, 303)
    selection = checked(client.get(personal))
    assert selection["has_authorization"] is True
    replay = client.get(callback.path + "?" + callback.query, follow_redirects=False)
    assert replay.status_code == 400


def approve(client: httpx.Client, connector_id: str, tools: list[dict[str, Any]]) -> None:
    url = f"/api/admin/connectors/mcp/{connector_id}/personal-tools"
    current = checked(client.get(url))
    checked(client.put(url, json={"expected_revision": current["revision"], "tools": tools}))


def activate(client: httpx.Client, connector_id: str) -> None:
    checked(client.put(f"/api/admin/connectors/mcp/{connector_id}/tools/activation", json={"tools": [{"tool_id": name, "activation_status": "enabled"} for name in ("echo_owner", "exclusive_alice")]}))


def discover(client: httpx.Client, connector_id: str) -> None:
    checked(client.post(f"/api/me/connectors/mcp/{connector_id}/tools/discovery", json={}), 204)


def proxy_token(url: str, token: str, fixture: httpx.Client) -> str:
    redirect_uri = "http://127.0.0.1:29876/callback"
    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    with httpx.Client(base_url=url.removesuffix("/mcp"), follow_redirects=False, timeout=30) as proxy:
        registration = checked(proxy.post("/register", json={"client_name": "Kind controlled identity client", "redirect_uris": [redirect_uri], "grant_types": ["authorization_code"], "response_types": ["code"], "token_endpoint_auth_method": "none"}), 201)
        state = secrets.token_urlsafe(24)
        response = proxy.get("/authorize", params={"client_id": registration["client_id"], "redirect_uri": redirect_uri, "response_type": "code", "state": state, "code_challenge": challenge, "code_challenge_method": "S256"})
        for _ in range(6):
            if response.status_code in (302, 303, 307):
                location = urlsplit(response.headers["location"])
                if location.hostname == "identity.personal-runtime.kind.invalid":
                    identity = fixture.get(location.path + "?" + location.query, headers={"Host": "identity.personal-runtime.kind.invalid", "Authorization": "Bearer " + token})
                    assert identity.status_code == 302
                    location = urlsplit(identity.headers["location"])
                if location.hostname == "127.0.0.1" and location.port == 29876:
                    parameters = parse_qs(location.query)
                    assert parameters["state"] == [state]
                    exchanged = checked(proxy.post("/token", data={"grant_type": "authorization_code", "client_id": registration["client_id"], "redirect_uri": redirect_uri, "code": parameters["code"][0], "code_verifier": verifier}))
                    access_token = str(exchanged["access_token"])
                    path = Path(os.environ["UMBOD_TEST_PERSONAL_PROXY_TOKENS"])
                    path.touch(mode=0o600)
                    with path.open("a") as saved:
                        saved.write(access_token + "\n")
                    return access_token
                cookie = "; ".join(f"{item.name}={item.value}" for item in proxy.cookies.jar)
                response = proxy.get(location.path + "?" + location.query, headers={"Cookie": cookie})
            else:
                assert response.status_code == 200
                fields = {name: html.unescape(value) for name, value in re.findall(r'name="([^"]+)" value="([^"]*)"', response.text)}
                assert "csrf_token" in fields
                fields["action"] = "approve"
                cookie = "; ".join(f"{item.name}={item.value}" for item in proxy.cookies.jar)
                response = proxy.post(response.request.url, data=fields, headers={"Cookie": cookie})
        raise AssertionError("Controlled upstream OAuth flow did not finish")


def mcp_client(url: str, token: str) -> Client[Any]:
    return Client(StreamableHttpTransport(url, headers={"Authorization": "Bearer " + token}))


async def find_tool(client: Client[Any], suffix: str) -> str:
    for _ in range(40):
        names = [tool.name for tool in await client.list_tools() if tool.name.endswith(suffix)]
        if len(names) == 1:
            return names[0]
        await asyncio.sleep(0.25)
    raise AssertionError("Approved personal tool did not become available")


async def denied(client: Client[Any], name: str, fixture: httpx.Client) -> None:
    before = checked(fixture.get("/control"))["calls"]
    result = await client.call_tool(name, {"message": "same-arguments"}, raise_on_error=False)
    assert result.is_error is True
    assert checked(fixture.get("/control"))["calls"] == before


async def owner_result(client: Client[Any], name: str, owner: str) -> None:
    result = await client.call_tool(name, {"message": "same-arguments"})
    payload = result.structured_content
    if payload is None:
        payload = json.loads(result.content[0].text)
    assert payload == {"owner": owner, "message": "same-arguments"}


@pytest.mark.asyncio
async def test_personal_oauth_execution_is_owner_bound_and_rechecks_live_policy(runtime_endpoints: RuntimeEndpoints) -> None:
    assert httpx.get(runtime_endpoints.api_base_url + "/api/me/connectors/mcp").status_code == 401
    with personal_clients(runtime_endpoints) as (alice, bob, fixture, connector_id):
        initial_counters = checked(fixture.get("/control"))
        health_url = f"/api/me/connectors/mcp/{connector_id}/authorization"
        assert checked(alice.get(health_url)) == {"state": "not_authorized"}
        authorize(alice, fixture, connector_id, "alice")
        authorize(bob, fixture, connector_id, "bob")
        assert checked(alice.get(health_url))["state"] == "authorized"
        assert checked(bob.get(health_url))["state"] == "authorized"
        assert checked(fixture.get("/control"))["exchanges"] == initial_counters["exchanges"] + 2
        tools = [contract(connector_id, name) for name in ("echo_owner", "exclusive_alice")]
        alice_mcp_token = proxy_token(runtime_endpoints.mcp_url, runtime_endpoints.bearer_token, fixture)
        bob_mcp_token = proxy_token(os.environ["UMBOD_TEST_MCP_B_URL"], os.environ["UMBOD_TEST_BEARER_TOKEN_B"], fixture)
        async with mcp_client(runtime_endpoints.mcp_url, alice_mcp_token) as a, mcp_client(os.environ["UMBOD_TEST_MCP_B_URL"], bob_mcp_token) as b:
            assert not any(tool.name.endswith("echo_owner") for tool in await a.list_tools())
            approve(alice, connector_id, tools)
            assert not any(tool.name.endswith("echo_owner") for tool in await a.list_tools())
            activate(alice, connector_id)
            assert not any(tool.name.endswith("echo_owner") for tool in await a.list_tools())
            grant(alice, connector_id, "enabled")
            assert not any(tool.name.endswith("echo_owner") for tool in await a.list_tools())
            assert checked(alice.get(f"/api/me/connectors/mcp/{connector_id}"))["runtime_available"] is False
            assert checked(bob.get(f"/api/me/connectors/mcp/{connector_id}"))["runtime_available"] is False
            discover(alice, connector_id)
            assert checked(alice.get(f"/api/me/connectors/mcp/{connector_id}"))["runtime_available"] is True
            assert checked(bob.get(f"/api/me/connectors/mcp/{connector_id}"))["runtime_available"] is False
            name = await find_tool(a, "echo_owner")
            exclusive = await find_tool(a, "exclusive_alice")
            assert not any(tool.name.endswith("echo_owner") for tool in await b.list_tools())
            await denied(b, name, fixture)
            discover(bob, connector_id)
            assert checked(bob.get(f"/api/me/connectors/mcp/{connector_id}"))["runtime_available"] is True
            assert await find_tool(b, "echo_owner") == name
            await owner_result(a, name, "alice")
            await owner_result(b, name, "bob")
            refresh_url = health_url + "/refresh"
            before_refresh = checked(fixture.get("/control"))
            assert checked(alice.get(health_url))["refresh_supported"] is True
            checked(fixture.post("/control", json={"owner": "alice", "mode": "refresh_hold"}))
            pending_refresh = asyncio.create_task(asyncio.to_thread(alice.post, refresh_url, json={}))
            try:
                with httpx.Client(base_url=os.environ["UMBOD_TEST_API_B_BASE_URL"], headers={"Authorization": f"Bearer {runtime_endpoints.bearer_token}"}, timeout=30) as second_worker:
                    for _ in range(50):
                        if checked(second_worker.get(health_url))["state"] == "refreshing":
                            break
                        await asyncio.sleep(0.1)
                    else:
                        raise AssertionError("Second REST worker did not observe durable refresh claim")
                    conflicting = second_worker.post(refresh_url, json={})
                    assert conflicting.status_code == 409
                    assert conflicting.json() == {"detail": {"code": "personal_refresh_conflict"}}
                    assert second_worker.post(f"/api/me/connectors/mcp/{connector_id}/oauth/attempts", json={}).status_code == 409
                    assert checked(second_worker.get(f"/api/me/connectors/mcp/{connector_id}"))["runtime_available"] is False
                    await denied(a, name, fixture)
                    assert checked(bob.get(f"/api/me/connectors/mcp/{connector_id}"))["runtime_available"] is True
            finally:
                checked(fixture.post("/control", json={"owner": "alice", "mode": "normal"}))
            refreshed = await pending_refresh
            assert refreshed.headers["cache-control"] == "no-store"
            assert checked(refreshed) == {"status": "refreshed", "discovery_required": True}
            after_refresh = checked(fixture.get("/control"))
            assert after_refresh["refreshes"] == before_refresh["refreshes"] + 1
            assert after_refresh["exchanges"] == before_refresh["exchanges"]
            assert after_refresh["discoveries"] == before_refresh["discoveries"]
            assert after_refresh["calls"] == before_refresh["calls"]
            assert checked(alice.get(f"/api/me/connectors/mcp/{connector_id}"))["runtime_available"] is False
            await denied(a, name, fixture)
            discover(alice, connector_id)
            await owner_result(a, name, "alice")
            await owner_result(a, exclusive, "alice")
            assert not any(tool.name == exclusive for tool in await b.list_tools())
            await denied(b, exclusive, fixture)
            public_policy = checked(alice.get(f"/api/admin/connectors/mcp/{connector_id}/personal-tools"))
            assert "Private inventory" not in json.dumps(public_policy)
            catalogue = checked(alice.get(f"/api/admin/connectors/mcp/{connector_id}/tools"))
            assert "Private inventory" not in json.dumps(catalogue)
            assert "Private Alice inventory" not in json.dumps(catalogue)
            for tool in await a.list_tools():
                if tool.name == name:
                    assert tool.description == "Administrator approved public contract"
            grant(alice, connector_id, "disabled")
            await denied(a, name, fixture)
            await denied(b, name, fixture)
            grant(alice, connector_id, "enabled")
            await owner_result(b, name, "bob")
            grant(alice, connector_id, "disabled", connector=True)
            await denied(a, name, fixture)
            await denied(b, name, fixture)
            grant(alice, connector_id, "enabled", connector=True)
            checked(alice.put(f"/api/me/connectors/mcp/{connector_id}/enablement", json={"enabled": False}))
            await denied(a, name, fixture)
            await owner_result(b, name, "bob")
            checked(alice.put(f"/api/me/connectors/mcp/{connector_id}/enablement", json={"enabled": True}))
            checked(alice.delete(f"/api/me/connectors/mcp/{connector_id}/authorization"), 204)
            assert checked(alice.get(f"/api/me/connectors/mcp/{connector_id}"))["runtime_available"] is False
            assert checked(bob.get(f"/api/me/connectors/mcp/{connector_id}"))["runtime_available"] is True
            await denied(a, name, fixture)
            await owner_result(b, name, "bob")
            before = checked(fixture.get("/control"))
            checked(fixture.post("/control", json={"owner": "bob", "mode": "unauthorized"}))
            result = await b.call_tool(name, {"message": "same-arguments"}, raise_on_error=False)
            assert result.is_error is True
            after = checked(fixture.get("/control"))
            assert after["unauthorized"] == before["unauthorized"] + 1
            assert after["calls"] == before["calls"]
            assert after["refreshes"] == before["refreshes"]
            assert after["exchanges"] == before["exchanges"]
            rejected_health = bob.get(health_url)
            assert rejected_health.headers["cache-control"] == "no-store"
            assert checked(rejected_health) == {"state": "reconnect_required", "reason": "provider_rejected"}
            assert checked(bob.get(f"/api/me/connectors/mcp/{connector_id}"))["runtime_available"] is False
            assert checked(alice.get(health_url)) == {"state": "not_authorized"}
            checked(fixture.post("/control", json={"owner": "bob", "mode": "normal"}))
            await denied(b, name, fixture)
            authorize(bob, fixture, connector_id, "bob")
            assert checked(bob.get(health_url))["state"] == "authorized"
            assert checked(bob.get(f"/api/me/connectors/mcp/{connector_id}"))["runtime_available"] is False
            await denied(b, name, fixture)
            discover(bob, connector_id)
            await owner_result(b, name, "bob")
            policy_url = f"/api/admin/connectors/mcp/{connector_id}/personal-oauth"
            policy = checked(alice.get(policy_url))
            settings = {"requested_scopes": [], "client": {"kind": "preconfigured_public", "issuer_url": ISSUER, "client_id": "kind-personal-client"}}
            rotated = checked(alice.put(policy_url, json={"expected_revision": policy["revision"], "settings": settings}))
            await denied(b, name, fixture)
            settings["requested_scopes"] = ["read"]
            checked(alice.put(policy_url, json={"expected_revision": rotated["revision"], "settings": settings}))
            authorize(bob, fixture, connector_id, "bob")
            discover(bob, connector_id)
            await owner_result(b, name, "bob")
            tools[0]["input_schema"]["properties"]["message"]["minLength"] = 1
            approve(alice, connector_id, tools)
            await denied(b, name, fixture)
        for token in (None, "invalid-user"):
            headers = {} if token is None else {"Authorization": "Bearer " + token}
            response = httpx.post(runtime_endpoints.mcp_url, headers=headers, json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
            assert response.status_code in (401, 403)
