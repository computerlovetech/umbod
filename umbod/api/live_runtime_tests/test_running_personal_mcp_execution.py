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
def personal_clients(
    endpoints: RuntimeEndpoints, client_configuration: dict[str, Any] | None = None,
) -> Iterator[tuple[httpx.Client, httpx.Client, httpx.Client, str]]:
    context = ssl.create_default_context(cafile=os.environ["UMBOD_TEST_PERSONAL_CA"])
    with httpx.Client(base_url=endpoints.api_base_url, headers={"Authorization": f"Bearer {endpoints.bearer_token}"}, timeout=90) as alice, httpx.Client(base_url=endpoints.api_base_url, headers={"Authorization": "Bearer " + os.environ["UMBOD_TEST_BEARER_TOKEN_B"]}, timeout=90) as bob, httpx.Client(base_url=os.environ["UMBOD_TEST_PERSONAL_URL"], verify=context, timeout=30, follow_redirects=False) as fixture:
        created = checked(alice.post("/api/admin/connectors/mcp/personal-oauth", json={"metadata": {"display_name": "Controlled personal runtime", "capability_description": "Controlled TLS interoperability", "public_path": "/mcp/proxies/runtime-" + uuid4().hex[:20]}, "configuration": {"endpoint_url": ISSUER + "/mcp", "oauth_configuration": {"requested_scopes": ["read"], "client": client_configuration if client_configuration is not None else {"kind": "preconfigured_public", "issuer_url": ISSUER, "client_id": "kind-personal-client"}}}}), 201)
        connector_id = created["connector_id"]
        admin = f"/api/admin/connectors/mcp/{connector_id}"
        try:
            before = checked(fixture.get("/control"))
            validate_setup(alice, connector_id)
            checked(alice.put(admin + "/publication"))
            grant(alice, connector_id, "enabled", connector=True)
            for client in (alice, bob):
                checked(client.put(f"/api/me/connectors/mcp/{connector_id}/enablement", json={"enabled": True}))
            assert checked(fixture.get("/control")) == before
            yield alice, bob, fixture, connector_id
        finally:
            grant(alice, connector_id, "disabled")
            grant(alice, connector_id, "disabled", connector=True)
            checked(alice.delete(admin + "/publication"))
            checked(alice.delete(admin), 204)


def validate_setup(client: httpx.Client, connector_id: str) -> None:
    policy_url = f"/api/admin/connectors/mcp/{connector_id}/personal-oauth"
    result = checked(client.post(policy_url + "/setup/validation", json={"expected_revision": client.get(policy_url + "/setup").json()["revision"]}))
    assert result["state"]["status"] == "validated"
    assert result["state"]["result"]["scope_source"] == "not_checked"
    assert result["state"]["result"]["returned_scopes"] == []


def grant(client: httpx.Client, connector_id: str, status: str, connector: bool = False) -> None:
    body = {"connectors": [{"connector_id": connector_id, "permission_status": status}]} if connector else {"capabilities": [{"connector_id": connector_id, "capability_kind": "tool", "capability_key": name, "permission_status": status} for name in ("echo_owner", "exclusive_alice")]}
    checked(client.put(PERMISSIONS, json=body))


def authorize(
    client: httpx.Client, fixture: httpx.Client, connector_id: str, owner: str,
    callback_client: httpx.Client | None = None,
) -> str:
    personal = f"/api/me/connectors/mcp/{connector_id}"
    started = checked(client.post(personal + "/oauth/attempts", json={}), 201)
    authorization = urlsplit(started["authorization_url"])
    consent = fixture.get(authorization.path + "?" + authorization.query + "&owner=" + owner)
    assert consent.status_code == 302
    callback = urlsplit(consent.headers["location"])
    assert callback.hostname == "umbod-runtime.kind.invalid"
    callback_worker = callback_client if callback_client is not None else client
    response = callback_worker.get(callback.path + "?" + callback.query, follow_redirects=False)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert "Sign-in complete" in response.text
    assert "Return to Umbod" in response.text
    assert "/dashboard" in response.text
    assert "unsafe-inline" not in response.headers["content-security-policy"]
    callback_parameters = parse_qs(callback.query)
    for parameter in ("code", "state"):
        assert callback_parameters[parameter][0] not in response.text
    selection = checked(client.get(personal))
    assert selection["has_authorization"] is True
    replay = client.get(callback.path + "?" + callback.query, follow_redirects=False)
    assert replay.status_code == 400
    assert replay.headers["content-type"].startswith("text/html")
    assert replay.headers["cache-control"] == "no-store"
    assert "Return to Umbod" in replay.text
    return parse_qs(authorization.query)["client_id"][0]


def approve(client: httpx.Client, connector_id: str, tools: list[dict[str, Any]]) -> None:
    url = f"/api/admin/connectors/mcp/{connector_id}/personal-tools"
    current = checked(client.get(url))
    checked(client.put(url, json={"expected_revision": current["revision"], "tools": tools}))


def activate(client: httpx.Client, connector_id: str, status: str) -> None:
    checked(client.put(f"/api/admin/connectors/mcp/{connector_id}/tools/activation", json={"tools": [{"tool_id": name, "activation_status": status} for name in ("echo_owner", "exclusive_alice")]}))


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
    raise AssertionError("Discovered personal tool did not become available")


async def wait_until_tool_hidden(client: Client[Any], name: str) -> None:
    for _ in range(40):
        if not any(tool.name == name for tool in await client.list_tools()):
            return
        await asyncio.sleep(0.25)
    raise AssertionError("Revoked personal tool remained visible")


async def denied(client: Client[Any], name: str, fixture: httpx.Client) -> None:
    before = checked(fixture.get("/control"))["calls"]
    result = await client.call_tool(name, {"message": "same-arguments"}, raise_on_error=False)
    assert result.is_error is True
    assert checked(fixture.get("/control"))["calls"] == before


async def recovery_required(client: Client[Any], name: str, fixture: httpx.Client, connector_id: str, instruction: str) -> None:
    before = checked(fixture.get("/control"))
    assert any(tool.name == name for tool in await client.list_tools())
    result = await client.call_tool(name, {"message": "same-arguments"}, raise_on_error=False)
    assert result.is_error is True
    assert result.structured_content is None
    message = " ".join(item.text for item in result.content if item.type == "text")
    assert instruction in message
    destination = urlsplit(message.split("Open ", 1)[1].split(" ", 1)[0])
    assert destination.scheme in ("https", "http")
    assert destination.hostname
    assert destination.username is None
    assert destination.password is None
    assert destination.path == "/connectors"
    assert parse_qs(destination.query) == {"connector": [f"downstream_mcp:{connector_id}"]}
    assert destination.fragment == ""
    after = checked(fixture.get("/control"))
    for counter in ("calls", "refreshes", "exchanges", "discoveries"):
        assert after[counter] == before[counter]


async def owner_result(client: Client[Any], name: str, owner: str) -> None:
    result = await client.call_tool(name, {"message": "same-arguments"})
    payload = result.structured_content
    if payload is None:
        payload = json.loads(result.content[0].text)
    assert payload == {"owner": owner, "message": "same-arguments"}


async def assert_private_inventory(client: Client[Any], owner: str, expected: tuple[str, ...]) -> None:
    tools = [tool for tool in await client.list_tools() if tool.name.endswith(("echo_owner", "exclusive_alice", "added_alice"))]
    assert len(tools) == len(expected)
    for suffix in expected:
        tool = next(tool for tool in tools if tool.name.endswith(suffix))
        description = {"echo_owner": f"Private inventory for {owner}", "exclusive_alice": "Private Alice inventory", "added_alice": "New private Alice inventory"}[suffix]
        assert tool.description == description
        assert tool.inputSchema["properties"]["message"]["type"] == "string"
        assert tool.inputSchema["required"] == ["message"]
        assert tool.outputSchema is not None
        assert tool.outputSchema["type"] == "object"


async def assert_added_tool(
    alice: httpx.Client, fixture: httpx.Client, connector_id: str, a: Client[Any], b: Client[Any],
) -> None:
    before = checked(fixture.get("/control"))
    checked(fixture.post("/control", json={"owner": "alice", "mode": "add_tool"}))
    assert not any(tool.name.endswith("added_alice") for tool in await a.list_tools())
    discover(alice, connector_id)
    added = await find_tool(a, "added_alice")
    assert checked(fixture.get("/control"))["calls"] == before["calls"]
    await owner_result(a, added, "alice")
    assert checked(fixture.get("/control"))["calls"] == before["calls"] + 1
    assert not any(tool.name == added for tool in await b.list_tools())
    await denied(b, added, fixture)
    checked(fixture.post("/control", json={"owner": "alice", "mode": "change_tool"}))
    await denied(a, added, fixture)
    discover(alice, connector_id)
    assert await find_tool(a, "added_alice") == added
    await owner_result(a, added, "alice")
    checked(fixture.post("/control", json={"owner": "alice", "mode": "add_tool"}))
    await denied(a, added, fixture)
    discover(alice, connector_id)
    assert await find_tool(a, "added_alice") == added
    await owner_result(a, added, "alice")
    assert checked(alice.get(f"/api/admin/connectors/mcp/{connector_id}/tools"))["tools"] == []
    assert checked(alice.get(f"/api/admin/connectors/mcp/{connector_id}/personal-tools"))["revision"] == "unconfigured"
    checked(fixture.post("/control", json={"owner": "alice", "mode": "normal"}))


async def assert_legacy_policy_is_metadata(
    alice: httpx.Client, fixture: httpx.Client, connector_id: str, a: Client[Any], b: Client[Any],
) -> None:
    tools = [contract(connector_id, name) for name in ("echo_owner", "exclusive_alice")]
    name = await find_tool(a, "echo_owner")
    before = checked(fixture.get("/control"))
    approve(alice, connector_id, tools)
    activate(alice, connector_id, "enabled")
    grant(alice, connector_id, "enabled")
    await owner_result(a, name, "alice")
    activate(alice, connector_id, "disabled")
    grant(alice, connector_id, "disabled")
    await owner_result(a, name, "alice")
    await owner_result(b, name, "bob")
    tools[0]["input_schema"]["properties"]["message"]["minLength"] = 100
    approve(alice, connector_id, tools)
    await owner_result(a, name, "alice")
    await owner_result(b, name, "bob")
    approve(alice, connector_id, [])
    await owner_result(a, name, "alice")
    await owner_result(b, name, "bob")
    assert checked(fixture.get("/control"))["calls"] == before["calls"] + 7
    assert checked(alice.get(f"/api/me/connectors/mcp/{connector_id}"))["runtime_available"] is True
    await assert_private_inventory(a, "alice", ("echo_owner", "exclusive_alice", "added_alice"))
    await assert_private_inventory(b, "bob", ("echo_owner",))


def public_callback(endpoints: RuntimeEndpoints, path: str, query: str) -> httpx.Response:
    return httpx.get(endpoints.api_base_url + path + "?" + query, follow_redirects=False, timeout=30)


@pytest.mark.parametrize("metadata_mode", ("issuer_omitted", "issuer_false"))
def test_issuer_bound_callback_accepts_absent_issuer_without_route_downgrade(
    runtime_endpoints: RuntimeEndpoints, metadata_mode: str,
) -> None:
    with personal_clients(runtime_endpoints) as (alice, _, fixture, connector_id):
        checked(fixture.post("/control", json={"owner": "metadata", "mode": metadata_mode}))
        try:
            personal = f"/api/me/connectors/mcp/{connector_id}"
            before = checked(fixture.get("/control"))
            started = checked(alice.post(personal + "/oauth/attempts", json={}), 201)
            authorization = urlsplit(started["authorization_url"])
            expected_path = "/api/oauth/downstream-mcp/callback/issuer/" + hashlib.sha256(ISSUER.encode("utf-8")).hexdigest()
            assert parse_qs(authorization.query)["redirect_uri"] == ["https://umbod-runtime.kind.invalid" + expected_path]
            consent = fixture.get(authorization.path + "?" + authorization.query + "&owner=alice")
            assert consent.status_code == 302
            callback = urlsplit(consent.headers["location"])
            assert callback.path == expected_path
            assert set(parse_qs(callback.query)) == {"code", "state"}
            attempt_url = personal + "/oauth/attempts/" + started["attempt_id"]
            wrong_paths = ("/api/oauth/downstream-mcp/callback", "/api/oauth/downstream-mcp/callback/issuer/" + "0" * 64)
            for wrong_path in wrong_paths:
                assert public_callback(runtime_endpoints, wrong_path, callback.query).status_code == 400
                assert checked(alice.get(attempt_url))["status"] == "pending"
            assert public_callback(runtime_endpoints, callback.path, callback.query + "&iss=" + ISSUER + "/").status_code == 400
            assert checked(alice.get(attempt_url))["status"] == "pending"
            assert checked(fixture.get("/control"))["exchanges"] == before["exchanges"]
            assert public_callback(runtime_endpoints, callback.path, callback.query).status_code == 200
            assert checked(alice.get(attempt_url))["status"] == "completed"
            assert checked(alice.get(personal + "/authorization"))["state"] == "authorized"
            assert checked(fixture.get("/control"))["exchanges"] == before["exchanges"] + 1
            assert public_callback(runtime_endpoints, callback.path, callback.query).status_code == 400
            assert checked(fixture.get("/control"))["exchanges"] == before["exchanges"] + 1
            checked(alice.post(personal + "/authorization/refresh", json={}))
            assert checked(fixture.get("/control"))["refreshes"] == before["refreshes"] + 1
        finally:
            checked(fixture.post("/control", json={"owner": "metadata", "mode": "normal"}))


@pytest.mark.parametrize("mode,status", (("refresh_denied", 409), ("refresh_uncertain", 503)))
def test_failed_refresh_requires_reconnect_without_provider_replay(
    runtime_endpoints: RuntimeEndpoints, mode: str, status: int,
) -> None:
    with personal_clients(runtime_endpoints) as (alice, _, fixture, connector_id):
        authorize(alice, fixture, connector_id, "alice")
        discover(alice, connector_id)
        personal = f"/api/me/connectors/mcp/{connector_id}"
        health_url = personal + "/authorization"
        before = checked(fixture.get("/control"))
        checked(fixture.post("/control", json={"owner": "alice", "mode": mode}))
        try:
            response = alice.post(health_url + "/refresh", json={})
            checked(response, status)
            assert response.headers["cache-control"] == "no-store"
            assert checked(alice.get(health_url)) == {"state": "reconnect_required", "reason": mode}
            assert checked(alice.get(personal))["runtime_available"] is False
            assert alice.post(health_url + "/refresh", json={}).status_code == 409
            after = checked(fixture.get("/control"))
            assert after["refreshes"] == before["refreshes"] + 1
            assert after["exchanges"] == before["exchanges"]
            assert after["calls"] == before["calls"]
            assert after["discoveries"] == before["discoveries"]
        finally:
            checked(fixture.post("/control", json={"owner": "alice", "mode": "normal"}))


@pytest.mark.asyncio
@pytest.mark.parametrize("metadata_mode,method", [
    ("confidential_basic", "client_secret_basic"),
    ("confidential_post", "client_secret_post"),
])
async def test_dynamic_confidential_registration_is_shared_across_users_and_workers(
    runtime_endpoints: RuntimeEndpoints, metadata_mode: str, method: str,
) -> None:
    context = ssl.create_default_context(cafile=os.environ["UMBOD_TEST_PERSONAL_CA"])
    configuration = {"kind": "dynamic_confidential", "approved_issuers": [ISSUER], "token_endpoint_auth_method": method}
    with httpx.Client(base_url=os.environ["UMBOD_TEST_PERSONAL_URL"], verify=context, timeout=30) as provider:
        checked(provider.post("/control", json={"owner": "metadata", "mode": metadata_mode}))
        try:
            initial = checked(provider.get("/control"))
            with personal_clients(runtime_endpoints, configuration) as (alice, bob, fixture, connector_id), httpx.Client(
                base_url=os.environ["UMBOD_TEST_API_B_BASE_URL"],
                headers={"Authorization": f"Bearer {runtime_endpoints.bearer_token}"}, timeout=90,
            ) as alice_worker_b:
                assert checked(fixture.get("/control")) == initial
                personal = f"/api/me/connectors/mcp/{connector_id}"
                policy = checked(alice.get(f"/api/admin/connectors/mcp/{connector_id}/personal-oauth"))
                assert policy["client"] == configuration
                checked(fixture.post("/control", json={"owner": "alice", "mode": "short_lived"}))
                alice_client_id = authorize(alice_worker_b, fixture, connector_id, "alice", callback_client=alice)
                after_alice = checked(fixture.get("/control"))
                assert after_alice["registrations"] == initial["registrations"] + 1
                assert after_alice["exchanges"] == initial["exchanges"] + 1
                bob_client_id = authorize(bob, fixture, connector_id, "bob")
                assert bob_client_id == alice_client_id
                assert checked(fixture.get("/control"))["registrations"] == after_alice["registrations"]
                discover(bob, connector_id)
                bob_selection = checked(bob.get(personal))
                for _ in range(100):
                    if checked(alice.get(personal + "/authorization"))["state"] == "expired":
                        break
                    await asyncio.sleep(0.1)
                else:
                    raise AssertionError("Short-lived authorization did not expire")
                checked(fixture.post("/control", json={"owner": "alice", "mode": "normal"}))
                before_refresh = checked(fixture.get("/control"))
                assert checked(alice_worker_b.post(personal + "/authorization/refresh", json={})) == {
                    "status": "refreshed", "discovery_required": True,
                }
                after_refresh = checked(fixture.get("/control"))
                assert after_refresh["refreshes"] == before_refresh["refreshes"] + 1
                assert after_refresh["registrations"] == after_alice["registrations"]
                assert after_refresh["exchanges"] == before_refresh["exchanges"]
                discover(alice, connector_id)
                alice_token = proxy_token(os.environ["UMBOD_TEST_MCP_B_URL"], runtime_endpoints.bearer_token, fixture)
                bob_token = proxy_token(runtime_endpoints.mcp_url, os.environ["UMBOD_TEST_BEARER_TOKEN_B"], fixture)
                async with mcp_client(os.environ["UMBOD_TEST_MCP_B_URL"], alice_token) as a, mcp_client(runtime_endpoints.mcp_url, bob_token) as b:
                    name = await find_tool(a, "echo_owner")
                    assert await find_tool(b, "echo_owner") == name
                    exclusive = await find_tool(a, "exclusive_alice")
                    assert not any(tool.name == exclusive for tool in await b.list_tools())
                    await owner_result(a, name, "alice")
                    await owner_result(b, name, "bob")
                    checked(alice_worker_b.delete(personal + "/authorization"), 204)
                    assert checked(alice.get(personal + "/authorization")) == {"state": "not_authorized"}
                    await denied(a, name, fixture)
                    assert checked(bob.get(personal)) == bob_selection
                    await owner_result(b, name, "bob")
                    assert checked(alice.get(personal))["enabled"] is False
                    assert checked(alice_worker_b.put(personal + "/enablement", json={"enabled": True}))["enabled"] is True
                    reconnected_client_id = authorize(alice_worker_b, fixture, connector_id, "alice", callback_client=alice)
                    assert reconnected_client_id == alice_client_id
                    discover(alice, connector_id)
                    await owner_result(a, name, "alice")
                final = checked(fixture.get("/control"))
                assert final["registrations"] == initial["registrations"] + 1
                assert final["exchanges"] == initial["exchanges"] + 3
                assert final["refreshes"] == initial["refreshes"] + 1
                for path in (personal, personal + "/authorization", f"/api/admin/connectors/mcp/{connector_id}/personal-oauth", f"/api/admin/connectors/mcp/{connector_id}/personal-oauth/setup"):
                    response = alice.get(path)
                    checked(response)
                    assert "kind-personal-dcr-secret-" not in response.text
        finally:
            checked(provider.post("/control", json={"owner": "alice", "mode": "normal"}))
            checked(provider.post("/control", json={"owner": "metadata", "mode": "normal"}))


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
        alice_mcp_token = proxy_token(runtime_endpoints.mcp_url, runtime_endpoints.bearer_token, fixture)
        bob_mcp_token = proxy_token(os.environ["UMBOD_TEST_MCP_B_URL"], os.environ["UMBOD_TEST_BEARER_TOKEN_B"], fixture)
        async with mcp_client(runtime_endpoints.mcp_url, alice_mcp_token) as a, mcp_client(os.environ["UMBOD_TEST_MCP_B_URL"], bob_mcp_token) as b:
            assert not any(tool.name.endswith("echo_owner") for tool in await a.list_tools())
            public_policy = checked(alice.get(f"/api/admin/connectors/mcp/{connector_id}/personal-tools"))
            assert public_policy == {"connector_id": connector_id, "revision": "unconfigured", "tools": []}
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
            await assert_private_inventory(a, "alice", ("echo_owner", "exclusive_alice"))
            await assert_private_inventory(b, "bob", ("echo_owner",))
            catalogue = checked(alice.get(f"/api/admin/connectors/mcp/{connector_id}/tools"))
            assert catalogue["tools"] == []
            await assert_added_tool(alice, fixture, connector_id, a, b)
            await assert_legacy_policy_is_metadata(alice, fixture, connector_id, a, b)
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
                    await recovery_required(a, name, fixture, connector_id, "recovery is in progress")
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
            await recovery_required(a, name, fixture, connector_id, "load tools")
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
            await assert_private_inventory(a, "alice", ("echo_owner", "exclusive_alice", "added_alice"))
            grant(alice, connector_id, "disabled", connector=True)
            await denied(a, name, fixture)
            await denied(b, name, fixture)
            await wait_until_tool_hidden(b, name)
            grant(alice, connector_id, "enabled", connector=True)
            assert await find_tool(a, "echo_owner") == name
            assert await find_tool(b, "echo_owner") == name
            await owner_result(a, name, "alice")
            await owner_result(b, name, "bob")
            bob_before_disable = checked(bob.get(f"/api/me/connectors/mcp/{connector_id}"))
            assert bob_before_disable["enabled"] is True
            assert bob_before_disable["runtime_available"] is True
            checked(alice.put(f"/api/me/connectors/mcp/{connector_id}/enablement", json={"enabled": False}))
            await denied(a, name, fixture)
            await owner_result(b, name, "bob")
            assert checked(bob.get(f"/api/me/connectors/mcp/{connector_id}")) == bob_before_disable
            checked(alice.put(f"/api/me/connectors/mcp/{connector_id}/enablement", json={"enabled": True}))
            checked(alice.delete(f"/api/me/connectors/mcp/{connector_id}/authorization"), 204)
            assert checked(alice.get(f"/api/me/connectors/mcp/{connector_id}"))["runtime_available"] is False
            assert checked(bob.get(f"/api/me/connectors/mcp/{connector_id}"))["runtime_available"] is True
            await denied(a, name, fixture)
            await owner_result(b, name, "bob")
            checked(fixture.post("/control", json={"owner": "bob", "mode": "forbidden"}))
            await denied(b, name, fixture)
            assert checked(bob.get(health_url))["state"] == "authorized"
            checked(fixture.post("/control", json={"owner": "bob", "mode": "normal"}))
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
            await recovery_required(b, name, fixture, connector_id, "Sign in again")
            authorize(bob, fixture, connector_id, "bob")
            assert checked(bob.get(health_url))["state"] == "authorized"
            assert checked(bob.get(f"/api/me/connectors/mcp/{connector_id}"))["runtime_available"] is False
            await recovery_required(b, name, fixture, connector_id, "load tools")
            discover(bob, connector_id)
            await owner_result(b, name, "bob")
            policy_url = f"/api/admin/connectors/mcp/{connector_id}/personal-oauth"
            policy = checked(alice.get(policy_url))
            settings = {"requested_scopes": [], "client": {"kind": "preconfigured_public", "issuer_url": ISSUER, "client_id": "kind-personal-client"}}
            rotated = checked(alice.put(policy_url, json={"expected_revision": policy["revision"], "settings": settings}))
            await denied(b, name, fixture)
            settings["requested_scopes"] = ["read"]
            checked(alice.put(policy_url, json={"expected_revision": rotated["revision"], "settings": settings}))
            validate_setup(alice, connector_id)
            checked(alice.put(f"/api/admin/connectors/mcp/{connector_id}/publication"))
            authorize(bob, fixture, connector_id, "bob")
            discover(bob, connector_id)
            await owner_result(b, name, "bob")
            checked(alice.delete(f"/api/admin/connectors/mcp/{connector_id}/publication"))
            await denied(b, name, fixture)
            checked(alice.put(f"/api/admin/connectors/mcp/{connector_id}/publication"))
            assert await find_tool(b, "echo_owner") == name
            await owner_result(b, name, "bob")
        for token in (None, "invalid-user"):
            headers = {} if token is None else {"Authorization": "Bearer " + token}
            response = httpx.post(runtime_endpoints.mcp_url, headers=headers, json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
            assert response.status_code == 401
