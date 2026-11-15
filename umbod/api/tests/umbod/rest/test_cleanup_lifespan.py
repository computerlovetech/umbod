import asyncio
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from umbod.config import AppConfig
from umbod.core.agent_behaviour.store import DatabaseAgentBehaviourStore
from umbod.core.usage.store import DatabaseUsageStore
from umbod.hosting import create_rest_app


@pytest.mark.asyncio
async def test_rest_lifespan_never_prunes_diagnostics_or_usage(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    declaration = tmp_path / "connectors.json"
    declaration.write_text('{"connectors": []}', encoding="utf-8")
    monkeypatch.setenv("UMBOD_CONNECTOR_DEPLOYMENT_CONFIGURATION_PATH", str(declaration))
    purge = AsyncMock(return_value=0)
    prune = AsyncMock()
    monkeypatch.setattr(DatabaseAgentBehaviourStore, "purge_expired", purge)
    monkeypatch.setattr(DatabaseUsageStore, "prune_usage", prune)
    settings = AppConfig(rest={"metrics_enabled": False}, admin_authentication={"mode": "disabled"})
    app = create_rest_app(settings, connector_registrations=[], admin_verifier=None, oauth_service=None)
    async with app.router.lifespan_context(app):
        await asyncio.sleep(0)
    purge.assert_not_awaited()
    prune.assert_not_awaited()
