from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator

from fastapi import FastAPI
from test_runtime import MemoryVault

from umbod_desktop import runtime
from umbod_desktop.backend_integration.configuration import desktop_settings
from umbod_desktop.settings import DesktopSettings
from umbod_desktop.storage import atomic_json


def test_configuration_maps_supplied_snapshot_without_reloading_profile(tmp_path: Path) -> None:
    atomic_json(tmp_path / "desktop-v2.json", {
        "version": 2, "servers": {},
        "settings": {"connector_tool_exposure_mode": "flat", "mcp_administrator_enabled": True},
    })
    snapshot = DesktopSettings(connector_tool_exposure_mode="codemode", mcp_administrator_enabled=False)
    config = desktop_settings(tmp_path, "http://127.0.0.1:8000", "root-secret", snapshot)
    assert config.mcp.connector_tool_exposure_mode == "codemode"
    assert config.feature_toggles.mcp_administrator_enabled is False


async def test_runtime_owns_administration_and_preserves_lifecycle_order(tmp_path: Path, monkeypatch: Any) -> None:
    events: list[str] = []
    config = object()
    snapshots: list[DesktopSettings] = []

    def map_config(directory: Path, origin: str, root: str, snapshot: DesktopSettings) -> object:
        snapshots.append(snapshot)
        return config

    def service(name: str) -> FastAPI:
        @asynccontextmanager
        async def lifespan(app: FastAPI) -> AsyncIterator[None]:
            events.append(name + ":enter")
            yield
            events.append(name + ":exit")
        return FastAPI(lifespan=lifespan)

    api = service("rest")
    mcp = service("mcp")

    def rest_factory(settings: object, **kwargs: Any) -> FastAPI:
        assert settings is config
        return api

    async def mcp_factory(settings: object, **kwargs: Any) -> FastAPI:
        assert settings is config
        return mcp

    class Administration:
        def __init__(self, application: FastAPI, token: str) -> None:
            assert application is api
            self.client = object()
            events.append("administration:create")

        async def close(self) -> None:
            events.append("administration:close")

    class Names:
        def __init__(self, administration: Administration, policy: object, prefix_repair: object) -> None:
            assert isinstance(administration, Administration)

        async def repair(self, state: object) -> None:
            events.append("names:repair")

    class Upstreams:
        def __init__(self, *args: Any) -> None:
            pass

        async def restore(self) -> None:
            events.append("upstreams:restore")

        async def close(self) -> None:
            events.append("upstreams:close")

    class OAuth:
        def __init__(self, *args: Any) -> None:
            pass

        async def close(self) -> None:
            events.append("oauth:close")

    monkeypatch.setattr(runtime, "desktop_settings", map_config)
    monkeypatch.setattr(runtime, "create_rest_app", rest_factory)
    monkeypatch.setattr(runtime, "create_mcp_app", mcp_factory)
    monkeypatch.setattr(runtime, "BackendAdministration", Administration)
    monkeypatch.setattr(runtime, "DesktopToolNames", Names)
    monkeypatch.setattr(runtime, "DesktopUpstreams", Upstreams)
    monkeypatch.setattr(runtime, "OAuthService", OAuth)
    monkeypatch.setattr(runtime, "DesktopOAuthHost", lambda upstreams: upstreams)
    app, token = await runtime.create_desktop_app(tmp_path, "dev", "http://127.0.0.1:8000", MemoryVault(), lambda: None)
    sent: list[dict[str, Any]] = []
    messages = iter([{"type": "lifespan.startup"}, {"type": "lifespan.shutdown"}])

    async def receive() -> dict[str, Any]:
        return next(messages)

    async def send(message: dict[str, Any]) -> None:
        sent.append(message)

    await app({"type": "lifespan", "state": {}}, receive, send)
    assert [message["type"] for message in sent] == ["lifespan.startup.complete", "lifespan.shutdown.complete"]
    assert snapshots == [DesktopSettings()]
    assert events == [
        "administration:create", "rest:enter", "names:repair", "mcp:enter", "upstreams:restore",
        "administration:close", "oauth:close", "upstreams:close", "mcp:exit", "rest:exit",
    ]
