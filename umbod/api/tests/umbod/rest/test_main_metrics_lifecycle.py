from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from tests.support.application_failures import CapturingApplicationFailures
from umbod.core.diagnostics import ApplicationFailureKind, NoFailureContext, report_application_failure
from umbod.rest.authentication.rest_middleware import RestAuthenticationMiddleware
from umbod.rest.main import create_app
from umbod.rest.metrics import AdminRestMetricsMiddleware
from umbod.rest.settings import APISettings
from umbod.rest.users.jwks import DisabledSigningKeyResolver


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
    path = tmp_path / "connector-availability.json"
    path.write_text('{"connectors": []}', encoding="utf-8")
    monkeypatch.setenv("UMBOD_CONNECTOR_DEPLOYMENT_CONFIGURATION_PATH", str(path))


class FailingMetricsServer(RecordingMetricsServer):
    async def start(self) -> None:
        self.start_count += 1
        raise RuntimeError("startup failed")


def test_rest_app_composes_one_shared_metrics_recorder_and_server(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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

    monkeypatch.setattr(
        "umbod.rest.main.PrometheusRestMetricsRecorder", create_recorder
    )
    monkeypatch.setattr("umbod.rest.main.RestMetricsHttpServer", create_server)
    settings = APISettings(admin_authentication={"mode": "simulation"})
    app = create_app(settings=settings, connector_registrations=[])
    metrics_middleware = next(
        (
            middleware
            for middleware in app.user_middleware
            if middleware.cls is AdminRestMetricsMiddleware
        )
    )
    assert len(recorders) == 1
    assert len(servers) == 1
    assert servers[0].recorder is recorders[0]
    assert servers[0].port == settings.rest.metrics_port
    assert metrics_middleware.kwargs["recorder"] is recorders[0]


def test_rest_metrics_server_starts_and_stops_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    server = RecordingMetricsServer(object(), 8001)
    settings = APISettings(connector_store={"type": "inmemory"})

    def create_server(recorder: object, port: int) -> RecordingMetricsServer:
        return server

    monkeypatch.setattr("umbod.rest.main.RestMetricsHttpServer", create_server)
    app = create_app(settings=settings, connector_registrations=[])
    with TestClient(app) as client:
        assert isinstance(
            client.app_state["profile_signing_key_resolver"], DisabledSigningKeyResolver
        )
        assert server.start_count == 1
        assert server.stop_count == 0
    assert server.stop_count == 1


def test_rest_metrics_server_is_cleaned_up_when_startup_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    server = FailingMetricsServer(object(), 8001)
    settings = APISettings(connector_store={"type": "inmemory"})

    def create_server(recorder: object, port: int) -> RecordingMetricsServer:
        return server

    monkeypatch.setattr("umbod.rest.main.RestMetricsHttpServer", create_server)
    app = create_app(settings=settings, connector_registrations=[])
    with pytest.raises(RuntimeError, match="startup failed"):
        with TestClient(app):
            pytest.fail("Application startup unexpectedly succeeded")
    assert server.start_count == 1
    assert server.stop_count == 1


def test_metrics_are_absent_from_rest_traffic_app(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("umbod.rest.main.RestMetricsHttpServer", RecordingMetricsServer)
    app = create_app(
        settings=APISettings(admin_authentication={"mode": "simulation"}),
        connector_registrations=[],
    )
    with TestClient(app) as client:
        assert client.get("/metrics").status_code == 404


def test_admin_metrics_middleware_wraps_authentication(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("umbod.rest.main.RestMetricsHttpServer", RecordingMetricsServer)
    app = create_app(
        settings=APISettings(admin_authentication={"mode": "simulation"}),
        connector_registrations=[],
    )
    middleware = app.user_middleware
    metrics_index = next(
        (
            index
            for (index, entry) in enumerate(middleware)
            if entry.cls is AdminRestMetricsMiddleware
        )
    )
    authentication_index = next(
        (
            index
            for (index, entry) in enumerate(middleware)
            if entry.cls is RestAuthenticationMiddleware
        )
    )
    assert metrics_index < authentication_index


def test_embedded_host_can_disable_metrics_without_changing_server_constructor(monkeypatch: pytest.MonkeyPatch) -> None:
    servers: list[RecordingMetricsServer] = []

    def create_server(recorder: object, port: int) -> RecordingMetricsServer:
        server = RecordingMetricsServer(recorder, port)
        servers.append(server)
        return server

    monkeypatch.setattr('umbod.rest.main.RestMetricsHttpServer', create_server)
    settings = APISettings(admin_authentication={'mode': 'simulation'}, connector_store={'type': 'inmemory'}, rest={'metrics_enabled': False})
    with TestClient(create_app(settings=settings, connector_registrations=[])) as client:
        assert client.get('/api/system/health').status_code == 200
    assert len(servers) == 1
    assert servers[0].start_count == 0
    assert servers[0].stop_count == 0


def test_two_rest_apps_have_isolated_application_failure_channels(
    caplog: pytest.LogCaptureFixture,
) -> None:
    settings = APISettings(admin_authentication={"mode": "simulation"})
    first = create_app(settings=settings, connector_registrations=[])
    second = create_app(settings=settings, connector_registrations=[])
    first_signal = next(
        middleware.kwargs["application_failures"]
        for middleware in first.user_middleware
        if middleware.cls is AdminRestMetricsMiddleware
    )
    second_signal = next(
        middleware.kwargs["application_failures"]
        for middleware in second.user_middleware
        if middleware.cls is AdminRestMetricsMiddleware
    )
    first_failures = CapturingApplicationFailures()
    second_failures = CapturingApplicationFailures()
    first_signal.connect("capture", first_failures.send)
    second_signal.connect("capture", second_failures.send)

    report_application_failure(
        first_signal, ApplicationFailureKind.REST_METRICS, RuntimeError("secret"), NoFailureContext(),
    )

    assert first_signal is not second_signal
    assert len(first_failures.events) == 1
    assert second_failures.events == []
    assert len(caplog.records) == 1

    report_application_failure(
        second_signal, ApplicationFailureKind.REST_METRICS, RuntimeError("secret"), NoFailureContext(),
    )

    assert len(first_failures.events) == 1
    assert len(second_failures.events) == 1
    assert len(caplog.records) == 2
