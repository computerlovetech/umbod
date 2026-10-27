import asyncio
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import httpx
import pytest
from starlette.testclient import TestClient

from umbod.hosting import (
    AppConfig,
    InMemoryGroupConnectorToolPermissions,
    JwtClaims,
    JwtVerificationError,
    McpToolInvocationEvent,
    create_mcp_app,
    create_rest_app,
)
from umbod.hosting import applications
from umbod.mcp import public_app


class OwnerVerifier:
    def __init__(self, owner: str) -> None:
        self.owner = owner

    def verify(self, token: str) -> JwtClaims:
        if token != self.owner:
            raise JwtVerificationError("Invalid token")
        return JwtClaims(claims={"sub": self.owner, "groups": ["owners"]})


class UsageSink:
    def record_invocation_completed(self, event: McpToolInvocationEvent) -> None:
        pass


@pytest.fixture
def settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AppConfig:
    declaration = tmp_path / "connectors.json"
    declaration.write_text('{"connectors": []}')
    monkeypatch.setenv("UMBOD_CONNECTOR_DEPLOYMENT_CONFIGURATION_PATH", str(declaration))
    return AppConfig.model_validate({
        "rest": {"metrics_enabled": False},
        "mcp": {"metrics_enabled": False, "auth_mode": "none"},
        "admin_authentication": {
            "mode": "jwt", "membership_claim": "groups",
            "required_membership": "owners",
        },
    })


def test_explicit_rest_settings_and_verifiers_are_isolated(
    settings: AppConfig, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("UMBOD_ADMIN_AUTH_MODE", "disabled")
    for owner in ("first", "second"):
        selected_settings = settings.model_copy(update={
            "admin_authentication": settings.admin_authentication.model_copy(update={
                "jwt_header_name": f"X-{owner}",
            }),
        })
        app = create_rest_app(selected_settings, connector_registrations=[], admin_verifier=OwnerVerifier(owner), oauth_service=None)
        with TestClient(app) as client:
            response = client.get("/api/admin/users", headers={f"X-{owner}": owner})
            assert response.status_code == 200
            assert response.json()["id"] == owner
            assert client.get("/api/admin/users", headers={f"X-{owner}": "wrong"}).status_code == 401
            assert client.get("/api/admin/users", headers={"X-other": owner}).status_code == 401
            assert client.get("/api/system/health").status_code == 200
            assert client.get("/admin/users").status_code == 404


@pytest.mark.asyncio
async def test_actual_mcp_app_serves_health_and_enters_lifespan(
    settings: AppConfig, monkeypatch: pytest.MonkeyPatch
) -> None:
    create_runtime = public_app.ConfiguredPersistenceRuntimeProvider.create
    shutdown = AsyncMock()

    def create_persistence(provider: public_app.ConfiguredPersistenceRuntimeProvider) -> Any:
        runtime = create_runtime(provider)
        shutdown.side_effect = runtime.shutdown
        return SimpleNamespace(database=runtime.database, readiness=runtime.readiness, shutdown=shutdown)

    monkeypatch.setattr(public_app.ConfiguredPersistenceRuntimeProvider, "create", create_persistence)
    app = await create_mcp_app(settings, auth_provider=None, group_permission_runtime_state=None, invocation_log_sink=None)
    shutdown.assert_not_awaited()
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as client:
            assert (await client.get("/system/health")).json() == {"status": "ok"}
            assert (await client.get("/.well-known/mcp/server-card.json")).status_code == 200
    shutdown.assert_awaited_once()


@dataclass(frozen=True)
class ConfigDouble:
    persistence_runtime: Any
    auth_provider: Any
    group_permission_runtime_state: Any
    invocation_log_sink: Any


@pytest.mark.asyncio
@pytest.mark.parametrize("override", [False, True])
async def test_mcp_overrides_preserve_configured_defaults(
    settings: AppConfig, monkeypatch: pytest.MonkeyPatch, override: bool
) -> None:
    configured = ConfigDouble(AsyncMock(), object(), object(), object())
    load = AsyncMock(return_value=configured)
    context = AsyncMock(return_value=object())
    build = AsyncMock(return_value=object())
    monkeypatch.setattr(applications, "load_configured_public_app_config", load)
    monkeypatch.setattr(applications, "create_runtime_context", context)
    monkeypatch.setattr(applications, "build_starlette_app", build)
    permissions = InMemoryGroupConnectorToolPermissions(group_claim_fields=("groups",))
    sink = UsageSink()
    auth = object()
    arguments = dict(auth_provider=auth, group_permission_runtime_state=permissions, invocation_log_sink=sink) if override else dict(auth_provider=None, group_permission_runtime_state=None, invocation_log_sink=None)
    result = await create_mcp_app(settings, **arguments)
    selected = context.await_args.args[0]
    assert selected.auth_provider is (auth if override else configured.auth_provider)
    assert selected.group_permission_runtime_state is (permissions if override else configured.group_permission_runtime_state)
    assert selected.invocation_log_sink is (sink if override else configured.invocation_log_sink)
    assert result is build.return_value
    load.assert_awaited_once_with(settings)
    configured.persistence_runtime.shutdown.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("stage", ["context", "app"])
@pytest.mark.parametrize("failure", [RuntimeError, asyncio.CancelledError])
async def test_mcp_construction_failure_closes_persistence(
    settings: AppConfig, monkeypatch: pytest.MonkeyPatch, stage: str, failure: type[BaseException]
) -> None:
    persistence = AsyncMock()
    config = ConfigDouble(persistence, None, None, None)
    monkeypatch.setattr(applications, "load_configured_public_app_config", AsyncMock(return_value=config))
    monkeypatch.setattr(applications, "create_runtime_context", AsyncMock(side_effect=failure() if stage == "context" else None))
    monkeypatch.setattr(applications, "build_starlette_app", AsyncMock(side_effect=failure()))
    with pytest.raises(failure):
        await create_mcp_app(settings, auth_provider=None, group_permission_runtime_state=None, invocation_log_sink=None)
    persistence.shutdown.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("stage", ["readiness", "runtime"])
@pytest.mark.parametrize("failure", [RuntimeError, asyncio.CancelledError])
async def test_configuration_acquisition_failure_closes_persistence(
    settings: AppConfig, monkeypatch: pytest.MonkeyPatch, stage: str, failure: type[BaseException]
) -> None:
    persistence = AsyncMock()
    persistence.readiness.ensure_ready.side_effect = failure() if stage == "readiness" else None
    monkeypatch.setattr(public_app.ConfiguredPersistenceRuntimeProvider, "create", lambda self: persistence)
    monkeypatch.setattr(public_app.DefaultConnectorRuntimeFactory, "create", AsyncMock(side_effect=failure()))
    with pytest.raises(failure):
        await create_mcp_app(settings, auth_provider=None, group_permission_runtime_state=None, invocation_log_sink=None)
    persistence.shutdown.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("stage", ["readiness", "runtime"])
async def test_task_cancellation_during_acquisition_closes_persistence(
    settings: AppConfig, monkeypatch: pytest.MonkeyPatch, stage: str
) -> None:
    entered = asyncio.Event()
    blocked = asyncio.Event()
    persistence = AsyncMock()

    async def wait_for_cancellation(*arguments: object) -> None:
        entered.set()
        await blocked.wait()

    monkeypatch.setattr(public_app.ConfiguredPersistenceRuntimeProvider, "create", lambda self: persistence)
    if stage == "readiness":
        persistence.readiness.ensure_ready.side_effect = wait_for_cancellation
    else:
        monkeypatch.setattr(public_app.DefaultConnectorRuntimeFactory, "create", wait_for_cancellation)
    task = asyncio.create_task(create_mcp_app(settings, auth_provider=None, group_permission_runtime_state=None, invocation_log_sink=None))
    await asyncio.wait_for(entered.wait(), timeout=5)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    persistence.shutdown.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [False, True])
async def test_rest_lifespan_does_not_close_host_owned_oauth(
    settings: AppConfig, monkeypatch: pytest.MonkeyPatch, failure: bool
) -> None:
    oauth = SimpleNamespace(close=AsyncMock())
    persistence = AsyncMock()
    if failure:
        persistence.readiness.ensure_ready.side_effect = RuntimeError("readiness failed")
    create_runtime = public_app.ConfiguredPersistenceRuntimeProvider.create

    def create_persistence(provider: public_app.ConfiguredPersistenceRuntimeProvider) -> Any:
        runtime = create_runtime(provider)
        return SimpleNamespace(database=runtime.database, readiness=persistence.readiness, shutdown=persistence.shutdown)

    monkeypatch.setattr(public_app.ConfiguredPersistenceRuntimeProvider, "create", create_persistence)
    app = create_rest_app(settings, connector_registrations=[], admin_verifier=OwnerVerifier("owner"), oauth_service=oauth)
    if failure:
        with pytest.raises(RuntimeError, match="readiness failed"):
            async with app.router.lifespan_context(app):
                pytest.fail("Startup should fail")
    else:
        async with app.router.lifespan_context(app):
            oauth.close.assert_not_awaited()
    oauth.close.assert_not_awaited()
    persistence.shutdown.assert_awaited_once()


@pytest.mark.asyncio
async def test_legacy_mcp_factories_delegate_to_hosting(
    settings: AppConfig, monkeypatch: pytest.MonkeyPatch
) -> None:
    build = AsyncMock(return_value=object())
    monkeypatch.setattr("umbod.hosting.create_mcp_app", build)
    monkeypatch.setattr(public_app, "load_server_app_config", lambda path: settings)
    assert await public_app.create_production_app() is build.return_value
    assert await public_app.create_configured_production_app(settings) is build.return_value
    assert build.await_count == 2
    build.assert_awaited_with(settings, auth_provider=None, group_permission_runtime_state=None, invocation_log_sink=None)
