import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from types import SimpleNamespace
from urllib.error import URLError

import pytest
from starlette.applications import Starlette
from starlette.types import Receive, Scope, Send

from umbod.mcp import public_app


class RecordingRuntimeStateSynchronizer:
    def __init__(self, events: list[str]) -> None:
        self._events = events
        self.attempts = 0

    async def sync_all(self) -> None:
        self.attempts += 1
        self._events.append(f'runtime-{self.attempts}')


class RecordingToolRuntimeStateSynchronizer:
    def __init__(self, events: list[str]) -> None:
        self._events = events
        self.attempts = 0

    async def sync_runtime_state(self, _tool_ref: object) -> None:
        self.attempts += 1
        self._events.append(f'tool-{self.attempts}')


class FailingGroupPermissionSynchronizer:
    def __init__(self, events: list[str], error: Exception) -> None:
        self._events = events
        self._error = error
        self.attempts = 0

    async def sync_group_permissions(self) -> None:
        self.attempts += 1
        self._events.append(f'group-{self.attempts}')
        if self.attempts == 1:
            raise self._error


class FakeReadiness:
    async def ensure_ready(self) -> None:
        return None


class FakePersistenceRuntime:
    def __init__(self) -> None:
        self.readiness = FakeReadiness()
        self.database = object()
        self.shutdown_called = False

    async def shutdown(self) -> None:
        self.shutdown_called = True


class FakeMetricsServer:
    async def start(self) -> None:
        return None

    async def stop(self) -> None:
        return None


class FakeHttpApp:
    async def __call__(self, _scope: Scope, _receive: Receive, _send: Send) -> None:
        return None

    @asynccontextmanager
    async def lifespan(self, _app: object) -> AsyncIterator[None]:
        yield


def _context() -> SimpleNamespace:
    return SimpleNamespace(
        settings=SimpleNamespace(
            endpoints=SimpleNamespace(mcp_base_url='http://mcp'),
            mcp=SimpleNamespace(metrics_port=0),
        ),
        connector_runtime=SimpleNamespace(
            connector_tool_mappings=[
                SimpleNamespace(connector_id='echo', operation_name='echo')
            ]
        ),
        group_permission_runtime_state=object(),
        api_base_url='http://api',
        persistence_runtime=FakePersistenceRuntime(),
        http_app=FakeHttpApp(),
        metrics_recorder=object(),
        mcp=SimpleNamespace(downstream_mcp_discovery_coordinator=None),
    )


async def _build_app_with_synchronizers(
    monkeypatch: pytest.MonkeyPatch,
    runtime_synchronizer: RecordingRuntimeStateSynchronizer,
    tool_synchronizer: RecordingToolRuntimeStateSynchronizer,
    group_synchronizer: FailingGroupPermissionSynchronizer,
) -> tuple[Starlette, SimpleNamespace]:
    context = _context()

    async def create_downstream_stores(*_args: object) -> SimpleNamespace:
        return SimpleNamespace(definitions=object(), publishing=object())

    async def record_sleep(_delay: float) -> None:
        return None

    monkeypatch.setattr(public_app, 'create_downstream_mcp_stores', create_downstream_stores)
    monkeypatch.setattr(
        public_app,
        'downstream_mcp_infrastructure_settings_from_app_config',
        lambda _settings: SimpleNamespace(credential_secret='test-credential-secret'),
    )
    monkeypatch.setattr(public_app, 'runtime_state_synchronizer_options', lambda _context: object())
    monkeypatch.setattr(public_app, 'create_connector_runtime_state_synchronizer', lambda _options: runtime_synchronizer)
    monkeypatch.setattr(public_app, 'create_connector_tool_runtime_state_synchronizer', lambda *_args: tool_synchronizer)
    monkeypatch.setattr(public_app, 'create_group_permission_runtime_synchronizer', lambda *_args: group_synchronizer)
    monkeypatch.setattr(public_app, 'create_connector_publication_synchronizer', lambda *_args: None)
    monkeypatch.setattr(public_app, 'create_connector_runtime_state_change_synchronizer', lambda *_args: None)
    monkeypatch.setattr(public_app, 'create_connector_tool_change_synchronizer', lambda *_args: None)
    monkeypatch.setattr(public_app, 'create_capability_description_override_synchronizer', lambda *_args: None)
    monkeypatch.setattr(public_app, 'create_group_permission_change_synchronizer', lambda *_args: None)
    monkeypatch.setattr(public_app, 'McpMetricsHttpServer', lambda *_args: FakeMetricsServer())
    monkeypatch.setattr(public_app.asyncio, 'sleep', record_sleep)
    return await public_app.build_starlette_app(context), context


@pytest.mark.asyncio
async def test_public_app_startup_retries_complete_initial_sequence_after_group_permission_url_error(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    events: list[str] = []
    app, context = await _build_app_with_synchronizers(
        monkeypatch,
        RecordingRuntimeStateSynchronizer(events),
        RecordingToolRuntimeStateSynchronizer(events),
        FailingGroupPermissionSynchronizer(events, URLError('temporarily unavailable')),
    )

    with caplog.at_level(logging.WARNING, logger=public_app.__name__):
        async with app.router.lifespan_context(app):
            pass

    assert events == [
        'runtime-1',
        'tool-1',
        'group-1',
        'runtime-2',
        'tool-2',
        'group-2',
    ]
    assert context.persistence_runtime.shutdown_called is True
    assert 'attempt 1' in caplog.text
    assert 'retrying in 1.0 seconds' in caplog.text
    assert 'temporarily unavailable' in caplog.text


@pytest.mark.asyncio
async def test_public_app_startup_fails_immediately_for_group_permission_non_url_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    app, context = await _build_app_with_synchronizers(
        monkeypatch,
        RecordingRuntimeStateSynchronizer(events),
        RecordingToolRuntimeStateSynchronizer(events),
        FailingGroupPermissionSynchronizer(events, ValueError('invalid permissions')),
    )

    with pytest.raises(ValueError, match='invalid permissions'):
        async with app.router.lifespan_context(app):
            pass

    assert events == ['runtime-1', 'tool-1', 'group-1']
    assert context.persistence_runtime.shutdown_called is True
