import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

import jwt
import pytest
from fastmcp import FastMCP
from fastmcp.server.auth import AccessToken, TokenVerifier
from starlette.testclient import TestClient

from umbod.core.callers import AuthenticationProvenance, CallerContext
from umbod.mcp.auth.caller import get_caller_context
from umbod.mcp.auth.local_test_auth import SingleTestUserOAuthProvider


class SubjectTokenVerifier(TokenVerifier):
    async def verify_token(self, token: str) -> Optional[AccessToken]:
        subjects = {"alice-token": "alice", "bob-token": "bob"}
        if token not in subjects:
            return None
        return AccessToken(
            token=token, client_id="client", scopes=[],
            claims={"iss": "https://issuer.example/", "sub": subjects[token]},
        )


def test_http_authentication_exposes_fresh_deployment_caller_observations() -> None:
    server = FastMCP("caller-test", auth=SubjectTokenVerifier(base_url="http://testserver"))

    @server.tool
    def current_caller() -> CallerContext:
        return get_caller_context(server)

    with TestClient(server.http_app(stateless_http=True, json_response=True)) as client:
        for subject in ("alice", "bob", "alice"):
            response = client.post(
                "/mcp", headers={
                    "Authorization": f"Bearer {subject}-token",
                    "Accept": "application/json, text/event-stream",
                }, json={"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {
                    "name": "current_caller", "arguments": {},
                }},
            )
            assert response.status_code == 200
            observation = response.json()["result"]["structuredContent"]
            assert observation == {
                "authentication": AuthenticationProvenance.DEPLOYMENT_AUTHENTICATED,
                "subject": {"issuer": {"value": "https://issuer.example/"}, "subject": subject},
            }
            assert f"{subject}-token" not in response.text


def test_concurrent_http_requests_keep_caller_contexts_isolated() -> None:
    server = FastMCP("caller-test", auth=SubjectTokenVerifier(base_url="http://testserver"))
    arrived = asyncio.Event()
    entered = 0

    @server.tool
    async def current_caller() -> dict[str, CallerContext]:
        nonlocal entered
        before = get_caller_context(server)
        entered += 1
        if entered == 2:
            arrived.set()
        await asyncio.wait_for(arrived.wait(), timeout=5)
        return {"before": before, "after": get_caller_context(server)}

    with TestClient(server.http_app(stateless_http=True, json_response=True)) as client:
        def observe(subject: str) -> dict[str, object]:
            response = client.post(
                "/mcp", headers={
                    "Authorization": f"Bearer {subject}-token",
                    "Accept": "application/json, text/event-stream",
                }, json={"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {
                    "name": "current_caller", "arguments": {},
                }},
            )
            response.raise_for_status()
            return response.json()["result"]["structuredContent"]

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(observe, subject) for subject in ("alice", "bob")]
            observations = [future.result(timeout=10) for future in futures]

    for subject, observations_for_subject in zip(("alice", "bob"), observations, strict=True):
        expected = {
            "authentication": AuthenticationProvenance.DEPLOYMENT_AUTHENTICATED,
            "subject": {"issuer": {"value": "https://issuer.example/"}, "subject": subject},
        }
        assert observations_for_subject == {"before": expected, "after": expected}


@pytest.mark.parametrize("local_test", [False, True])
def test_http_absence_and_local_test_authentication_have_explicit_provenance(local_test: bool) -> None:
    token = jwt.encode({"email": "local@example.com", "sub": "local-user"}, "local-test-secret-for-caller-context-only")
    provider = SingleTestUserOAuthProvider(token, "http://localhost") if local_test else None
    server = FastMCP("caller-test", auth=provider)

    @server.tool
    def current_caller() -> CallerContext:
        return get_caller_context(server)

    headers = {"Accept": "application/json, text/event-stream"}
    if local_test:
        headers["Authorization"] = f"Bearer {token}"
    with TestClient(server.http_app(stateless_http=True, json_response=True), base_url="http://localhost") as client:
        response = client.post(
            "/mcp", headers=headers,
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {
                "name": "current_caller", "arguments": {},
            }},
        )
    assert response.status_code == 200
    context = response.json()["result"]["structuredContent"]
    assert context["authentication"] == (
        AuthenticationProvenance.LOCAL_TEST if local_test else AuthenticationProvenance.UNAVAILABLE
    )
    assert context["subject"] == (
        {"issuer": {"kind": "unavailable"}, "subject": "local-user"}
        if local_test else {"kind": "unavailable"}
    )
