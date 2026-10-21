import asyncio
import base64
import hashlib
import json
from pathlib import Path
import secrets
import time

import jwt
from contextlib import AsyncExitStack, asynccontextmanager
from typing import Any, AsyncIterator
from urllib.parse import urlencode, parse_qs

import uvicorn
from fastmcp import FastMCP
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, RedirectResponse, Response
from starlette.routing import Route

ISSUER = "https://personal-runtime.kind.invalid"
RESOURCE = ISSUER + "/mcp"
identity_codes: dict[str, dict[str, str]] = {}
codes: dict[str, dict[str, str]] = {}
tokens: dict[str, str] = {}
refresh_tokens: dict[str, str] = {}
counters: dict[str, int] = {"calls": 0, "exchanges": 0, "refreshes": 0, "unauthorized": 0, "discoveries": 0}
modes: dict[str, str] = {}
refresh_release: dict[str, asyncio.Event] = {}


def owner_server(owner: str) -> FastMCP:
    server = FastMCP("Controlled personal resource")

    @server.tool(description=f"Private inventory for {owner}")
    def echo_owner(message: str) -> dict[str, str]:
        counters["calls"] += 1
        return {"owner": owner, "message": message}

    if owner == "alice":
        @server.tool(description="Private Alice inventory")
        def exclusive_alice(message: str) -> dict[str, str]:
            counters["calls"] += 1
            return {"owner": owner, "message": message}
    return server


apps = {owner: owner_server(owner).http_app(path="/mcp", stateless_http=True, json_response=True) for owner in ("alice", "bob")}


@asynccontextmanager
async def lifespan(app: Starlette) -> AsyncIterator[None]:
    async with AsyncExitStack() as stack:
        for downstream in apps.values():
            await stack.enter_async_context(downstream.lifespan(downstream))
        yield


async def metadata(request: Request) -> Response:
    if request.url.hostname == "identity.personal-runtime.kind.invalid":
        issuer = "https://identity.personal-runtime.kind.invalid/"
        if request.url.path == "/.well-known/jwks.json":
            return JSONResponse(json.loads(Path("/fixture/jwks.json").read_text()))
        if request.url.path == "/.well-known/openid-configuration":
            return JSONResponse({"issuer": issuer, "jwks_uri": issuer + ".well-known/jwks.json", "authorization_endpoint": issuer + "authorize", "token_endpoint": issuer + "oauth/token", "response_types_supported": ["code"], "subject_types_supported": ["public"], "id_token_signing_alg_values_supported": ["RS256"], "token_endpoint_auth_methods_supported": ["client_secret_basic", "client_secret_post"], "code_challenge_methods_supported": ["S256"]})
        return JSONResponse({"error": "not_found"}, status_code=404)
    if "oauth-protected-resource" in request.url.path:
        return JSONResponse({"resource": RESOURCE, "authorization_servers": [ISSUER], "scopes_supported": ["read"], "bearer_methods_supported": ["header"]})
    return JSONResponse({"issuer": ISSUER, "authorization_endpoint": ISSUER + "/authorize", "token_endpoint": ISSUER + "/token", "response_types_supported": ["code"], "grant_types_supported": ["authorization_code", "refresh_token"], "token_endpoint_auth_methods_supported": ["none"], "code_challenge_methods_supported": ["S256"], "authorization_response_iss_parameter_supported": True})


async def identity_authorize(request: Request) -> Response:
    parameters = dict(request.query_params)
    token = request.headers.get("authorization", "").removeprefix("Bearer ")
    key = jwt.PyJWK.from_dict(json.loads(Path("/fixture/jwks.json").read_text())["keys"][0])
    try:
        claims = jwt.decode(token, key.key, algorithms=["RS256"], audience="kind-client", issuer="https://identity.personal-runtime.kind.invalid/")
    except jwt.InvalidTokenError:
        return JSONResponse({"error": "invalid_token"}, status_code=401)
    if parameters.get("client_id") != "kind-client" or parameters.get("redirect_uri") != "https://mcp.umbod.example.invalid/auth/callback" or claims["sub"] not in ("kind-ci", "kind-ci-b"):
        return JSONResponse({"error": "invalid_request"}, status_code=400)
    code = secrets.token_urlsafe(32)
    identity_codes[code] = {**parameters, "sub": claims["sub"]}
    return RedirectResponse(parameters["redirect_uri"] + "?" + urlencode({"code": code, "state": parameters["state"]}), status_code=302)


async def identity_exchange(request: Request) -> Response:
    if request.url.hostname != "identity.personal-runtime.kind.invalid":
        return JSONResponse({"error": "not_found"}, status_code=404)
    parameters = {key: values[0] for key, values in parse_qs((await request.body()).decode()).items()}
    client = parameters.get("client_id", "") + ":" + parameters.get("client_secret", "")
    basic = "Basic " + base64.b64encode(b"kind-client:kind-disposable-identity-client-secret").decode()
    if client != "kind-client:kind-disposable-identity-client-secret" and request.headers.get("authorization") != basic:
        return JSONResponse({"error": "invalid_client"}, status_code=401)
    saved = identity_codes.pop(parameters.get("code", ""), {})
    if parameters.get("grant_type") != "authorization_code" or not saved or parameters.get("redirect_uri") != saved["redirect_uri"]:
        return JSONResponse({"error": "invalid_grant"}, status_code=400)
    if "code_challenge" in saved:
        digest = base64.urlsafe_b64encode(hashlib.sha256(parameters.get("code_verifier", "").encode()).digest()).rstrip(b"=").decode()
        if saved.get("code_challenge_method") != "S256" or digest != saved["code_challenge"]:
            return JSONResponse({"error": "invalid_grant"}, status_code=400)
    issued = int(time.time())
    token = jwt.encode({"sub": saved["sub"], "email": saved["sub"] + "@example.invalid", "groups": ["admin"], "scope": "openid profile email groups", "iss": "https://identity.personal-runtime.kind.invalid/", "aud": "kind-client", "iat": issued, "exp": issued + 3600}, Path("/identity/identity.key").read_bytes(), algorithm="RS256", headers={"kid": "kind-personal-jwt"})
    return JSONResponse({"access_token": token, "token_type": "Bearer", "expires_in": 3600, "scope": "openid profile email groups"})


async def authorize(request: Request) -> Response:
    if request.url.hostname == "identity.personal-runtime.kind.invalid":
        return await identity_authorize(request)
    parameters = dict(request.query_params)
    owner = parameters.pop("owner", "")
    if owner not in apps or parameters.get("client_id") != "kind-personal-client" or parameters.get("code_challenge_method") != "S256" or parameters.get("resource") != RESOURCE or parameters.get("redirect_uri") != "https://umbod-runtime.kind.invalid/api/oauth/downstream-mcp/callback":
        return JSONResponse({"error": "invalid_request"}, status_code=400)
    code = secrets.token_urlsafe(32)
    codes[code] = {**parameters, "owner": owner}
    return RedirectResponse(parameters["redirect_uri"] + "?" + urlencode({"code": code, "state": parameters["state"], "iss": ISSUER}), status_code=302)


async def exchange(request: Request) -> Response:
    parameters = {key: values[0] for key, values in parse_qs((await request.body()).decode()).items()}
    if parameters.get("grant_type") == "refresh_token":
        counters["refreshes"] += 1
        owner = refresh_tokens.pop(parameters.get("refresh_token", ""), "")
        if not owner or parameters.get("client_id") != "kind-personal-client" or parameters.get("resource") != RESOURCE or "scope" in parameters:
            return JSONResponse({"error": "invalid_grant"}, status_code=400)
        mode = modes.get(owner, "normal")
        if mode == "refresh_hold":
            await refresh_release[owner].wait()
        if mode == "refresh_slow":
            await asyncio.sleep(2)
        if mode == "refresh_denied":
            return JSONResponse({"error": "invalid_grant"}, status_code=400)
        if mode == "refresh_uncertain":
            return JSONResponse({"error": "temporarily_unavailable"}, status_code=503)
        token = "kind-personal-downstream-token-" + secrets.token_urlsafe(32)
        refresh = "kind-personal-refresh-token-" + secrets.token_urlsafe(32)
        tokens[token] = owner
        refresh_tokens[refresh] = owner
        return JSONResponse({"access_token": token, "token_type": "Bearer", "expires_in": 3600, "scope": "read", "refresh_token": refresh})
    if parameters.get("grant_type") != "authorization_code":
        return JSONResponse({"error": "unsupported_grant_type"}, status_code=400)
    saved = codes.pop(parameters.get("code", ""), {})
    digest = base64.urlsafe_b64encode(hashlib.sha256(parameters.get("code_verifier", "").encode()).digest()).rstrip(b"=").decode()
    if not saved or digest != saved["code_challenge"] or any(parameters.get(key) != saved[key] for key in ("resource", "redirect_uri", "client_id")):
        return JSONResponse({"error": "invalid_grant"}, status_code=400)
    counters["exchanges"] += 1
    token = "kind-personal-downstream-token-" + secrets.token_urlsafe(32)
    tokens[token] = saved["owner"]
    refresh = "kind-personal-refresh-token-" + secrets.token_urlsafe(32)
    refresh_tokens[refresh] = saved["owner"]
    return JSONResponse({"access_token": token, "token_type": "Bearer", "expires_in": 3600, "scope": "read", "refresh_token": refresh})


async def control(request: Request) -> Response:
    if request.method == "POST":
        payload = await request.json()
        owner = payload["owner"]
        modes[owner] = payload["mode"]
        if payload["mode"] == "refresh_hold":
            refresh_release[owner] = asyncio.Event()
        elif owner in refresh_release:
            refresh_release[owner].set()
    return JSONResponse(counters)


router = Starlette(routes=[Route("/.well-known/{path:path}", metadata), Route("/authorize", authorize), Route("/token", exchange, methods=["POST"]), Route("/oauth/token", identity_exchange, methods=["POST"]), Route("/control", control, methods=["GET", "POST"]), Route("/health", control)], lifespan=lifespan)


async def application(scope: dict[str, Any], receive: Any, send: Any) -> None:
    if scope["type"] == "http" and scope["path"] == "/mcp":
        token = dict(scope["headers"]).get(b"authorization", b"").decode().removeprefix("Bearer ")
        owner = tokens.get(token)
        if owner is None or modes.get(owner) == "unauthorized":
            counters["unauthorized"] += 1
            response = JSONResponse({"error": "invalid_token"}, status_code=401, headers={"WWW-Authenticate": f'Bearer resource_metadata="{ISSUER}/.well-known/oauth-protected-resource/mcp"'})
            await response(scope, receive, send)
            return
        if scope["method"] == "POST":
            body = await Request(scope, receive).body()
            try:
                if json.loads(body).get("method") == "tools/list":
                    counters["discoveries"] += 1
            except (ValueError, AttributeError):
                pass

            body_delivered = False

            async def replay_body() -> dict[str, Any]:
                nonlocal body_delivered
                if body_delivered:
                    return await receive()
                body_delivered = True
                return {"type": "http.request", "body": body, "more_body": False}

            await apps[owner](scope, replay_body, send)
            return
        await apps[owner](scope, receive, send)
        return
    await router(scope, receive, send)


if __name__ == "__main__":
    uvicorn.run(application, host="0.0.0.0", port=8443, ssl_certfile="/tls/tls.crt", ssl_keyfile="/tls/tls.key", access_log=False, log_level="warning")
