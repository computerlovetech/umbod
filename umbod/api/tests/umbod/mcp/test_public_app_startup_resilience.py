import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from urllib.error import URLError

import pytest
from starlette.applications import Starlette

from umbod.mcp import public_app
from umbod.mcp.messaging import RuntimeProjectionHealth, RuntimeProjectionSynchronizer
from umbod.mcp.runtime_options import StoreBackedConnectorRuntimeStateSourceStrategy


class FakeHttpApp:
    @asynccontextmanager
    async def lifespan(self, _app: object) -> AsyncIterator[None]:
        yield


def _context() -> SimpleNamespace:
    return SimpleNamespace(
        api_base_url=None,
        source_strategy=StoreBackedConnectorRuntimeStateSourceStrategy(),
        settings=SimpleNamespace(mcp=SimpleNamespace(messaging_transport='sql', metrics_port=0, metrics_enabled=False)),
        persistence_runtime=SimpleNamespace(readiness=SimpleNamespace(ensure_ready=AsyncMock()), shutdown=AsyncMock()),
        http_app=FakeHttpApp(),
        metrics_recorder=object(),
        mcp=SimpleNamespace(runtime_projection_health=RuntimeProjectionHealth(), downstream_mcp_discovery_coordinator=None),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize('failure', [URLError('source unavailable'), ValueError('invalid projection')])
async def test_failed_projection_bootstrap_never_enters_ready_lifespan_and_closes_persistence(monkeypatch: pytest.MonkeyPatch, failure: Exception) -> None:
    context = _context()
    synchronizer = Mock(spec=RuntimeProjectionSynchronizer)
    synchronizer.bootstrap.side_effect = failure
    monkeypatch.setattr(public_app, '_create_runtime_projection_synchronizer', lambda _context: synchronizer)
    app = Starlette(lifespan=public_app._create_public_http_lifespan(context))
    with pytest.raises(type(failure)):
        async with app.router.lifespan_context(app):
            pytest.fail('Failed bootstrap must not expose MCP')
    assert not context.mcp.runtime_projection_health.ready
    synchronizer.run.assert_not_called()
    context.persistence_runtime.shutdown.assert_awaited_once()


@pytest.mark.asyncio
async def test_lifespan_cancels_its_projection_consumer_before_closing_persistence(monkeypatch: pytest.MonkeyPatch) -> None:
    context = _context()
    started = asyncio.Event()
    cancelled = asyncio.Event()

    async def run() -> None:
        started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            cancelled.set()
            raise

    synchronizer = Mock(spec=RuntimeProjectionSynchronizer)
    synchronizer.run.side_effect = run
    monkeypatch.setattr(public_app, '_create_runtime_projection_synchronizer', lambda _context: synchronizer)
    app = Starlette(lifespan=public_app._create_public_http_lifespan(context))
    async with app.router.lifespan_context(app):
        await asyncio.wait_for(started.wait(), timeout=1)
        context.persistence_runtime.shutdown.assert_not_awaited()
    assert cancelled.is_set()
    synchronizer.bootstrap.assert_awaited_once()
    synchronizer.stop.assert_called_once()
    context.persistence_runtime.shutdown.assert_awaited_once()
