"""Compose existing REST/MCP applications with desktop-only lifecycle routes."""

import os
import sys
from collections.abc import AsyncIterator, Callable
from contextlib import AsyncExitStack, asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from starlette.applications import Starlette
from starlette.routing import Route
from starlette.types import ASGIApp
from umbod.hosting import (
    InMemoryGroupConnectorToolPermissions,
    OAuthService,
    create_mcp_app,
    create_rest_app,
)

from .backend_integration.administration import BackendAdministration
from .backend_integration.authentication import (
    DesktopAdminVerifier,
    DesktopAgentVerifier,
)
from .backend_integration.configuration import desktop_settings
from .backend_integration.naming import BackendToolNamingPolicy
from .backend_integration.oauth import (
    DesktopOAuthHost,
    callback_transport,
)
from .backend_integration.transports import DesktopUpstreams
from .backend_integration.usage import DesktopUsageSink
from .backward_compatibility.adapters.administration import BackendPrefixRepair
from .backward_compatibility.adapters.oauth import KeychainLegacyAuthorizationImporter
from .backward_compatibility.authentication import LegacyAgentCredentials
from .backward_compatibility.migration import DesktopMigration
from .backward_compatibility.profile import saved_agent_hashes
from .backward_compatibility.tool_names import DesktopToolNames
from .client_setup import ClientSetup
from .contracts import UpstreamInput
from .security import (
    CredentialVault,
    LoopbackAuthentication,
    persistent_secret,
)
from .settings import DesktopSettings
from .storage import DesktopState, atomic_json
from .usage import DesktopUsageRecorder


async def create_desktop_app(
    directory: Path, profile: str, origin: str, vault: CredentialVault,
    shutdown: Callable[[], None],
) -> tuple[ASGIApp, str]:
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
    state = DesktopState(directory)
    effective_settings = state.settings
    settings = desktop_settings(directory, origin, root, effective_settings)
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
    api = create_rest_app(settings, connector_registrations=None, admin_verifier=DesktopAdminVerifier(admin_token), oauth_service=oauth)
    administration = BackendAdministration(api, admin_token)
    tool_names = DesktopToolNames(administration, BackendToolNamingPolicy(), BackendPrefixRepair(administration.client))
    migration = DesktopMigration(
        directory, state, upstreams, administration, tool_names,
        KeychainLegacyAuthorizationImporter(vault),
    )
    mcp = await create_mcp_app(
        settings,
        invocation_log_sink=DesktopUsageSink(DesktopUsageRecorder(state)),
        auth_provider=DesktopAgentVerifier(
            agent_token, LegacyAgentCredentials(tuple(state.data["legacy_agent_hashes"]))
        ),
        group_permission_runtime_state=InMemoryGroupConnectorToolPermissions(
            group_claim_fields=("groups",)
        ),
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        async with AsyncExitStack() as stack:
            await stack.enter_async_context(api.router.lifespan_context(api))
            await tool_names.repair(state)
            await stack.enter_async_context(mcp.router.lifespan_context(mcp))
            await upstreams.restore()
            stack.push_async_callback(upstreams.close)
            stack.push_async_callback(oauth.close)
            stack.push_async_callback(administration.close)
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
    async def prepare(request: Request) -> dict[str, Any]:
        try:
            return (await upstreams.prepare(UpstreamInput(await request.json()))).model_dump()
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
