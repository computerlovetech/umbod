from umbod.infrastructure import ConfiguredPersistenceRuntimeProvider
from pathlib import Path
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from umbod.rest.authentication import AdminAuthenticationMiddleware
from umbod.rest.main import _create_lifespan, create_app
from umbod.rest.metrics import AdminRestMetricsMiddleware
from umbod.rest.settings import APISettings

class RecordingMetricsServer:

    def __init__(self, recorder: object, port: int) -> None:
        self.recorder = recorder
        self.port = port
        self.start_count = 0
        self.stop_count = 0

    async def start(self) -> None:
        self.start_count += 1

    async def stop(self) -> None:
        self.stop_count += 1

@pytest.fixture(autouse=True)
def connector_availability(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / 'connector-availability.json'
    path.write_text('{"connectors": []}', encoding='utf-8')
    monkeypatch.setenv('UMBOD_CONNECTOR_DEPLOYMENT_CONFIGURATION_PATH', str(path))

class FailingMetricsServer(RecordingMetricsServer):

    async def start(self) -> None:
        self.start_count += 1
        raise RuntimeError('startup failed')

def _admin_app(app: FastAPI) -> FastAPI:
    for route in app.routes:
        if getattr(route, 'path', None) == '/admin':
            return route.app
    raise AssertionError('admin application is not mounted')

def test_rest_app_composes_one_shared_metrics_recorder_and_server(monkeypatch: pytest.MonkeyPatch) -> None:
    recorders: list[object] = []
    servers: list[RecordingMetricsServer] = []

    def create_recorder() -> object:
        recorder = object()
        recorders.append(recorder)
        return recorder

    def create_server(recorder: object, port: int) -> RecordingMetricsServer:
        server = RecordingMetricsServer(recorder, port)
        servers.append(server)
        return server
    monkeypatch.setattr('umbod.rest.main.PrometheusRestMetricsRecorder', create_recorder)
    monkeypatch.setattr('umbod.rest.main.RestMetricsHttpServer', create_server)
    settings = APISettings(admin_authentication={'mode': 'simulation'})
    app = create_app(settings=settings, connector_registrations=[])
    admin_app = _admin_app(app)
    metrics_middleware = next((middleware for middleware in admin_app.user_middleware if middleware.cls is AdminRestMetricsMiddleware))
    assert len(recorders) == 1
    assert len(servers) == 1
    assert servers[0].recorder is recorders[0]
    assert servers[0].port == settings.rest.metrics_port
    assert metrics_middleware.kwargs['recorder'] is recorders[0]

def test_rest_metrics_server_starts_and_stops_once(tmp_path: Path) -> None:
    server = RecordingMetricsServer(object(), 8001)
    settings = APISettings(connector_store={'type': 'sqlite', 'sqlite_path': str(tmp_path / 'api.sqlite3')})
    runtime = ConfiguredPersistenceRuntimeProvider(settings.connector_store).create()
    app = FastAPI(lifespan=_create_lifespan(server, runtime))
    with TestClient(app):
        assert server.start_count == 1
        assert server.stop_count == 0
    assert server.stop_count == 1

@pytest.mark.asyncio
async def test_rest_metrics_server_is_cleaned_up_when_startup_fails(tmp_path: Path) -> None:
    server = FailingMetricsServer(object(), 8001)
    settings = APISettings(connector_store={'type': 'sqlite', 'sqlite_path': str(tmp_path / 'api.sqlite3')})
    app = FastAPI()
    with pytest.raises(RuntimeError, match='startup failed'):
        runtime = ConfiguredPersistenceRuntimeProvider(settings.connector_store).create()
        async with _create_lifespan(server, runtime)(app):
            pass
    assert server.start_count == 1
    assert server.stop_count == 1

def test_metrics_are_absent_from_rest_traffic_app(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr('umbod.rest.main.RestMetricsHttpServer', RecordingMetricsServer)
    app = create_app(settings=APISettings(admin_authentication={'mode': 'simulation'}), connector_registrations=[])
    with TestClient(app) as client:
        assert client.get('/metrics').status_code == 404

def test_admin_metrics_middleware_wraps_authentication(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr('umbod.rest.main.RestMetricsHttpServer', RecordingMetricsServer)
    app = create_app(settings=APISettings(admin_authentication={'mode': 'simulation'}), connector_registrations=[])
    middleware = _admin_app(app).user_middleware
    metrics_index = next((index for (index, entry) in enumerate(middleware) if entry.cls is AdminRestMetricsMiddleware))
    authentication_index = next((index for (index, entry) in enumerate(middleware) if entry.cls is AdminAuthenticationMiddleware))
    assert metrics_index < authentication_index
