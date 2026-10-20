import asyncio
import json
import socket
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
import pytest
import uvicorn
from test_runtime import MemoryVault

from umbod_desktop.backend_integration.configuration import desktop_settings
from umbod_desktop.runtime import create_desktop_app
from umbod_desktop.storage import DesktopState


def test_existing_profile_defaults_ignore_operator_environment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    original = {
        "version": 2,
        "servers": {},
        "migration": {"status": "complete"},
        "legacy_agent_hashes": ["retained"],
        "client_setup": {"saved": True},
    }
    path = tmp_path / "desktop-v2.json"
    path.write_text(json.dumps(original))
    monkeypatch.setenv("UMBOD_MCP_TOOL_EXPOSURE", "flat")
    monkeypatch.setenv("UMBOD_FEATURE_MCP_ADMINISTRATOR_ENABLED", "true")
    config = desktop_settings(tmp_path, "http://127.0.0.1:8000", "test-root", DesktopState(tmp_path).settings)
    assert config.mcp.connector_tool_exposure_mode == "gateway"
    assert config.feature_toggles.mcp_administrator_enabled is False
    assert DesktopState(tmp_path).data == original


def test_saved_settings_drive_backend_composition(tmp_path: Path) -> None:
    original = {
        "version": 2,
        "servers": {"saved": {"id": "keep"}},
        "settings": {
            "connector_tool_exposure_mode": "flat",
            "mcp_administrator_enabled": True,
        },
        "migration": {"status": "complete"},
        "legacy_agent_hashes": ["keep"],
    }
    (tmp_path / "desktop-v2.json").write_text(json.dumps(original))
    config = desktop_settings(tmp_path, "http://127.0.0.1:8000", "test-root", DesktopState(tmp_path).settings)
    assert config.mcp.connector_tool_exposure_mode == "flat"
    assert config.feature_toggles.mcp_administrator_enabled is True
    assert DesktopState(tmp_path).data == original


@pytest.mark.parametrize(
    "settings",
    [
        None,
        [],
        {"connector_tool_exposure_mode": "unknown"},
        {"mcp_administrator_enabled": 1},
    ],
)
def test_malformed_saved_settings_fail_closed_without_rewriting(tmp_path, settings):
    path = tmp_path / "desktop-v2.json"
    original = json.dumps({"version": 2, "servers": {"keep": {}}, "settings": settings})
    path.write_text(original)
    with pytest.raises(ValueError, match="Desktop settings"):
        DesktopState(tmp_path)
    assert path.read_text() == original


@asynccontextmanager
async def running_backend(directory, vault):
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen(128)
        origin = f"http://127.0.0.1:{listener.getsockname()[1]}"
        app, token = await create_desktop_app(
            directory, "dev", origin, vault, lambda: None
        )
        server = uvicorn.Server(uvicorn.Config(app, log_level="error"))
        task = asyncio.create_task(server.serve(sockets=[listener]))
        try:
            async with asyncio.timeout(30):
                while not server.started:
                    if task.done():
                        await task
                    await asyncio.sleep(0.02)
            async with httpx.AsyncClient(
                base_url=origin, headers={"Authorization": f"Bearer {token}"}
            ) as client:
                yield client, origin
        finally:
            server.should_exit = True
            await task


async def test_settings_api_is_pending_authenticated_and_durable(tmp_path):
    legacy = {
        "version": 2,
        "servers": {},
        "migration": {"status": "complete"},
        "diagnostics": {"enabled": True},
        "legacy_agent_hashes": [],
    }
    (tmp_path / "desktop-v2.json").write_text(json.dumps(legacy))
    vault = MemoryVault()
    async with running_backend(tmp_path, vault) as (client, origin):
        response = await client.get("/desktop/settings")
        assert response.status_code == 200
        defaults = {
            "connector_tool_exposure_mode": "gateway",
            "mcp_administrator_enabled": False,
        }
        assert response.json() == {
            "pending": defaults,
            "effective": defaults,
            "restart_required": False,
        }
        assert DesktopState(tmp_path).data["settings"] == defaults
        for token in ("wrong", vault.get("python:agent-token")):
            for method in ("GET", "PUT"):
                denied = await client.request(
                    method,
                    "/desktop/settings",
                    headers={"Authorization": f"Bearer {token}"},
                    json=defaults,
                )
                assert denied.status_code == 401
        selected = {
            "connector_tool_exposure_mode": "codemode",
            "mcp_administrator_enabled": True,
        }
        saved = await client.put("/desktop/settings", json=selected)
        assert saved.status_code == 200
        assert saved.json() == {
            "pending": selected,
            "effective": defaults,
            "restart_required": True,
        }
        assert (await client.get("/desktop/settings")).json() == saved.json()
        assert DesktopState(tmp_path).data["settings"] == selected
        for invalid in (
            {**selected, "connector_tool_exposure_mode": "typo"},
            {**selected, "mcp_administrator_enabled": "false"},
            {**selected, "extra": True},
            None,
            [],
        ):
            assert (
                await client.put("/desktop/settings", json=invalid)
            ).status_code == 422
        assert (await client.get("/desktop/settings")).json() == saved.json()
    credentials = dict(vault.values)
    async with running_backend(tmp_path, vault) as (client, origin):
        assert (await client.get("/desktop/settings")).json() == {
            "pending": selected,
            "effective": selected,
            "restart_required": False,
        }
        assert (await client.get("/desktop/health")).json()["status"] == "ok"
    assert vault.values == credentials
    assert all(
        DesktopState(tmp_path).data[key] == value for key, value in legacy.items()
    )


async def test_failed_settings_write_keeps_memory_and_disk_unchanged(
    tmp_path, monkeypatch
):
    vault = MemoryVault()
    async with running_backend(tmp_path, vault) as (client, origin):
        before = (await client.get("/desktop/settings")).json()
        document = (tmp_path / "desktop-v2.json").read_bytes()

        def fail_write(path, value):
            raise OSError("Fixture disk full")

        with monkeypatch.context() as context:
            context.setattr("umbod_desktop.runtime.atomic_json", fail_write)
            failed = await client.put(
                "/desktop/settings",
                json={
                    "connector_tool_exposure_mode": "flat",
                    "mcp_administrator_enabled": True,
                },
            )
            assert failed.status_code == 500
        assert (await client.get("/desktop/settings")).json() == before
        assert (tmp_path / "desktop-v2.json").read_bytes() == document
        # The owner can retry without rebuilding the profile.
        assert (
            await client.put(
                "/desktop/settings",
                json={
                    "connector_tool_exposure_mode": "flat",
                    "mcp_administrator_enabled": True,
                },
            )
        ).status_code == 200
