"""Compose existing REST/MCP applications with desktop-only lifecycle routes."""

import os
import sys
from contextlib import AsyncExitStack, asynccontextmanager
from dataclasses import replace
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from starlette.applications import Starlette
from starlette.routing import Route
from umbod.core.connectors.downstream_mcp.oauth.service import OAuthService
from umbod.core.permissions import InMemoryGroupConnectorToolPermissions
from umbod.mcp.public_app import (
    build_starlette_app,
    create_runtime_context,
    load_configured_public_app_config,
)
from umbod.rest.main import create_app

from .client_setup import ClientSetup
from .configuration import desktop_settings
from .legacy import saved_agent_hashes
from .migration import DesktopMigration
from .oauth import DesktopOAuthHost, callback_transport
from .security import (
    CredentialVault,
    DesktopAdminVerifier,
    DesktopAgentVerifier,
    LoopbackAuthentication,
    persistent_secret,
)
from .settings import DesktopSettings
from .storage import DesktopState, atomic_json
from .upstreams import DesktopUpstreams
from .usage import DesktopUsageSink


async def create_desktop_app(
    directory: Path, profile: str, origin: str, vault: CredentialVault, shutdown
):
    declaration = directory / "native-connectors.json"
    atomic_json(declaration, {"connectors": []})
    os.environ["UMBOD_CONNECTOR_DEPLOYMENT_CONFIGURATION_PATH"] = str(declaration)
    if (directory / "backend.sqlite3").exists() and vault.get(
        "python:root-secret"
    ) is None:
        raise ValueError(
            "The backend encryption key is missing from Keychain; restore it before opening existing data"
        )
    root = persistent_secret(vault, "python:root-secret")
    admin_token = persistent_secret(vault, "python:admin-token")
    agent_token = persistent_secret(vault, "python:agent-token")
    upstream_token = persistent_secret(vault, "python:upstream-token")
    settings = desktop_settings(directory, origin, root)
    state = DesktopState(directory)
    if state.data.get("profile", profile) != profile:
        raise ValueError("Desktop profile does not match its data directory")
    state.data["profile"] = profile
    state.data.setdefault("settings", state.settings.model_dump())
    if "legacy_agent_hashes" not in state.data:
        state.data["legacy_agent_hashes"] = saved_agent_hashes(directory)
    state.save()
    upstreams = DesktopUpstreams(state, vault, upstream_token, origin)
    oauth = OAuthService(DesktopOAuthHost(upstreams))
    callback = callback_transport(oauth)
    client_setup = ClientSetup(state, directory, profile)
    callbacks = Starlette(
        routes=[Route("/desktop/oauth/callback/{nonce}", callback),
        Route("/desktop/oauth/callback", callback)]
    )
    api = create_app(settings, admin_verifier=DesktopAdminVerifier(admin_token), oauth_service=oauth)
    migration = DesktopMigration(directory, state, upstreams, api, admin_token)
    config = await load_configured_public_app_config(settings)
    config = replace(
        config,
        invocation_log_sink=DesktopUsageSink(state),
        auth_provider=DesktopAgentVerifier(
            agent_token, tuple(state.data["legacy_agent_hashes"])
        ),
        group_permission_runtime_state=InMemoryGroupConnectorToolPermissions(
            group_claim_fields=("groups",)
        ),
    )
    context = await create_runtime_context(config)
    mcp = await build_starlette_app(context)

    @asynccontextmanager
    async def lifespan(app):
        async with AsyncExitStack() as stack:
            await stack.enter_async_context(api.router.lifespan_context(api))
            await migration.tool_names.repair(state)
            await stack.enter_async_context(mcp.router.lifespan_context(mcp))
            await upstreams.restore()
            stack.push_async_callback(upstreams.close)
            stack.push_async_callback(oauth.close)
            stack.push_async_callback(migration.close)
            yield

    host = FastAPI(docs_url=None, openapi_url=None, lifespan=lifespan)

    @host.get("/desktop/health")
    async def health():
        return {
            "status": "ok",
            "profile": profile,
            "pid": os.getpid(),
            "backend": "python",
            "protocol": 2,
            "build_id": (Path(sys.executable).parent.parent.parent / "runtime-id")
            .read_text()
            .strip()
            if (Path(sys.executable).parent.parent.parent / "runtime-id").exists()
            else "development",
        }

    effective_settings = DesktopSettings(
        connector_tool_exposure_mode=settings.mcp.connector_tool_exposure_mode,
        mcp_administrator_enabled=settings.feature_toggles.mcp_administrator_enabled,
    )

    @host.get("/desktop/settings")
    async def read_settings():
        pending = state.settings
        return {
            "pending": pending.model_dump(),
            "effective": effective_settings.model_dump(),
            "restart_required": pending != effective_settings,
        }

    @host.put("/desktop/settings")
    async def save_settings(pending: DesktopSettings):
        # Persist before publishing the new pending value. Failed writes leave both
        # the running configuration and in-memory metadata untouched.
        updated = {**state.data, "settings": pending.model_dump()}
        atomic_json(state.path, updated)
        state.data = updated
        return await read_settings()

    @host.post("/desktop/shutdown")
    async def stop():
        shutdown()
        return {"status": "stopping"}

    @host.post("/desktop/migration")
    async def migrate():
        await migration.run()
        return state.data.get("migration", {"status": "not_needed"})

    @host.get("/desktop/state")
    async def desktop_state():
        return state.data

    @host.post("/desktop/upstreams")
    async def prepare(request: Request):
        try:
            return await upstreams.prepare(await request.json())
        except (ValueError, KeyError):
            raise HTTPException(
                422, "Invalid desktop connector or missing credential"
            ) from None

    @host.post("/desktop/upstreams/{key}/restart")
    async def restart_upstream(key: str):
        if key not in state.data["servers"]:
            raise HTTPException(404)
        try:
            await upstreams.start(key, state.data["servers"][key])
        except (ValueError, OSError):
            raise HTTPException(
                422,
                "Restore the connector executable or Keychain credential, then retry",
            ) from None
        state.data.setdefault("transport_errors", {}).pop(key, None)
        state.save()
        return {"status": "restarted"}

    @host.put("/desktop/upstreams/{key}/binding")
    async def bind(key: str, request: Request):
        if key not in state.data["servers"]:
            raise HTTPException(404)
        body = await request.json()
        state.data["servers"][key]["id"] = body["connector_id"]
        state.save()
        return {"status": "saved"}

    @host.delete("/desktop/upstreams/{key}")
    async def remove(key: str):
        await oauth.forget(key)
        lifetime = upstreams.lifetimes.pop(key, None)
        if lifetime:
            await lifetime.aclose()
        upstreams.apps.pop(key, None)
        state.data["servers"].pop(key, None)
        state.data.setdefault("transport_errors", {}).pop(key, None)
        state.save()
        return {"status": "removed"}

    @host.put("/desktop/credentials/{reference:path}")
    async def set_credential(reference: str, request: Request):
        if not reference.startswith("upstream:"):
            raise HTTPException(422, "Invalid credential reference")
        value = (await request.json()).get("value")
        if not isinstance(value, str) or not value:
            raise HTTPException(422, "A credential value is required")
        vault.set(reference, value)
        return {"status": "saved"}

    @host.delete("/desktop/credentials/{reference:path}")
    async def delete_credential(reference: str):
        if not reference.startswith("upstream:"):
            raise HTTPException(422, "Invalid credential reference")
        vault.delete(reference)
        return {"status": "deleted"}

    @host.get("/desktop/connection")
    async def connection():
        return {"token": agent_token, "url": f"{origin}/mcp"}

    @host.post("/desktop/actions")
    async def actions(request: Request):
        body = await request.json()
        action = body.get("action")
        if action in ("client_preview", "client_apply", "client_undo"):
            try:
                return {
                    "client_preview": client_setup.preview,
                    "client_apply": client_setup.apply,
                    "client_undo": client_setup.undo,
                }[action](body)
            except (ValueError, TypeError, KeyError, OSError):
                raise HTTPException(
                    409,
                    "Agent configuration could not be updated. Check the file and preview again; any saved backup is preserved.",
                ) from None
        if action == "diagnostics_set":
            state.data["diagnostics"] = {"enabled": bool(body.get("enabled"))}
            state.save()
            return state.data["diagnostics"]
        raise HTTPException(422, "Unsupported desktop action")

    # Host guard protects system routes and documentation as well as administration.
    host.mount("/", api)
    guarded_host = LoopbackAuthentication(host, admin_token)

    class Dispatcher:
        async def __call__(self, scope, receive, send):
            path = scope.get("path", "")
            if scope["type"] == "http" and (path == "/desktop/oauth/callback" or path.startswith("/desktop/oauth/callback/")):
                await callbacks(scope, receive, send)
            elif (
                scope["type"] == "http"
                and path.startswith("/desktop/upstreams/")
                and path.endswith("/mcp")
            ):
                await upstreams(scope, receive, send)
            elif scope["type"] == "http" and (
                path == "/mcp" or path.startswith("/mcp/")
            ):
                await mcp(scope, receive, send)
            else:
                await guarded_host(scope, receive, send)

    return Dispatcher(), admin_token
