import json
from typing import Optional

import pytest
from fastapi import APIRouter, FastAPI, Request, Response
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from tests.support.application_failures import CapturingApplicationFailures
from umbod.core.diagnostics import ApplicationFailure
from umbod.core.signals import SignalPublisher
from umbod.logging import create_application_failure_signal
from umbod.logging import OpenTelemetryJsonFormatter
from umbod.rest.authentication import AdminAuthenticationMiddleware
from umbod.rest.metrics import (
    AdminRestMetricsMiddleware,
    CompletedRestRequest,
    RestMetricsRecorder,
)
from tests.support.rest_metrics import InMemoryRestMetricsRecorder


class RejectingAuthenticationStrategy:
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code

    async def authenticate(self, request: Request) -> Optional[Response]:
        return JSONResponse({"detail": "rejected"}, status_code=self.status_code)


def create_test_app(
    recorder: RestMetricsRecorder,
    authentication_status: Optional[int] = None,
    *, application_failures: SignalPublisher[ApplicationFailure],
) -> FastAPI:
    router = APIRouter()

    @router.get("/items/{item_id}")
    async def read_item(item_id: str) -> dict[str, str]:
        return {"item_id": item_id}

    @router.get("/client-error")
    async def client_error() -> Response:
        return JSONResponse({}, status_code=422)

    @router.get("/server-error")
    async def server_error() -> Response:
        return JSONResponse({}, status_code=503)

    @router.get("/exception")
    async def exception() -> Response:
        raise RuntimeError("route failed")

    app = FastAPI()
    app.include_router(router)
    if authentication_status is not None:
        app.add_middleware(
            AdminAuthenticationMiddleware,
            strategy=RejectingAuthenticationStrategy(authentication_status),
        )
    app.add_middleware(AdminRestMetricsMiddleware, recorder=recorder, routes=router.routes, mount_path="", application_failures=application_failures)
    return app


def test_records_completed_admin_responses_by_normalized_route_and_status_class() -> None:
    recorder = InMemoryRestMetricsRecorder()
    client = TestClient(create_test_app(recorder, application_failures=create_application_failure_signal()))

    assert client.get("/items/private-user?token=secret").status_code == 200
    assert client.get("/client-error").status_code == 422
    assert client.get("/server-error").status_code == 503

    samples = recorder.metric_samples()
    count_samples = [sample for sample in samples if sample.name.endswith("requests_total")]
    assert {
        (sample.labels["route"], sample.labels["status_class"]) for sample in count_samples
    } == {
        ("/admin/items/{item_id}", "2xx"),
        ("/admin/client-error", "4xx"),
        ("/admin/server-error", "5xx"),
    }
    assert "private-user" not in str(samples)
    assert "secret" not in str(samples)


@pytest.mark.parametrize("status_code", [401, 403])
def test_records_authentication_rejections_for_matched_routes(status_code: int) -> None:
    recorder = InMemoryRestMetricsRecorder()
    app = create_test_app(recorder, status_code, application_failures=create_application_failure_signal())

    assert app.user_middleware[0].cls is AdminRestMetricsMiddleware
    assert app.user_middleware[1].cls is AdminAuthenticationMiddleware
    assert TestClient(app).get("/items/alpha").status_code == status_code
    assert recorder.metric_samples()[0].labels == {
        "method": "GET",
        "route": "/admin/items/{item_id}",
        "status_class": "4xx",
    }


def test_excludes_unmatched_and_non_admin_app_requests() -> None:
    recorder = InMemoryRestMetricsRecorder()
    admin_client = TestClient(create_test_app(recorder, application_failures=create_application_failure_signal()))
    root_app = FastAPI()

    @root_app.get("/system/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    assert admin_client.get("/unknown/private-user").status_code == 404
    assert TestClient(root_app).get("/system/health").status_code == 200
    assert recorder.metric_samples() == ()


def test_unknown_methods_use_bounded_other_label() -> None:
    recorder = InMemoryRestMetricsRecorder()

    response = TestClient(create_test_app(recorder, application_failures=create_application_failure_signal())).request("CUSTOM", "/items/alpha")

    assert response.status_code == 405
    assert recorder.metric_samples()[0].labels["method"] == "OTHER"


def test_metrics_failure_publishes_without_logging(caplog: pytest.LogCaptureFixture) -> None:
    class FailingRecorder:
        def record_completed_request(self, request: CompletedRestRequest) -> None:
            raise ValueError("secret-canary")

    failures = CapturingApplicationFailures()
    app = create_test_app(FailingRecorder(), application_failures=failures)

    response = TestClient(app).get("/items/private-id?token=secret-canary")

    assert response.status_code == 200
    assert caplog.records == []
    assert len(failures.events) == 1
    event = failures.events[0]
    attributes = dict(event.attributes)
    assert attributes["normalized_route"] == "/admin/items/{item_id}"
    assert attributes["status_code"] == 200
    assert attributes["method"] == "GET"
    assert "private-id" not in event.model_dump_json()
    assert "secret-canary" not in event.model_dump_json()


def test_metrics_failure_preserves_response(caplog: pytest.LogCaptureFixture) -> None:
    class FailingRecorder:
        def record_completed_request(self, request: CompletedRestRequest) -> None:
            raise ValueError("secret-canary")

    with caplog.at_level("ERROR"):
        response = TestClient(create_test_app(FailingRecorder(), application_failures=create_application_failure_signal())).get("/items/alpha")

    assert response.status_code == 200
    assert response.json() == {"item_id": "alpha"}
    assert "REST metrics recording failed" in caplog.text
    serialized = OpenTelemetryJsonFormatter("test").format(caplog.records[-1])
    assert "secret-canary" not in serialized
    assert json.loads(serialized)["attributes"]["exception.type"] == "ValueError"
    assert json.loads(serialized)["attributes"]["normalized_route"] == "/admin/items/{item_id}"


def test_metrics_model_validation_failure_preserves_response(
    caplog: pytest.LogCaptureFixture,
) -> None:
    router = APIRouter()

    @router.get("/items/{item_id}#metrics")
    async def read_item(item_id: str) -> dict[str, str]:
        return {"item_id": item_id}

    app = FastAPI()
    app.include_router(router)
    recorder = InMemoryRestMetricsRecorder()
    app.add_middleware(AdminRestMetricsMiddleware, recorder=recorder, routes=router.routes, mount_path="", application_failures=create_application_failure_signal())

    with caplog.at_level("ERROR"):
        response = TestClient(app).get("/items/alpha%23metrics")

    assert response.status_code == 200
    assert response.json() == {"item_id": "alpha"}
    assert "REST metrics recording failed" in caplog.text
    assert recorder.metric_samples() == ()
    failure_records = [
        record
        for record in caplog.records
        if record.levelname == "ERROR" and record.getMessage() == "REST metrics recording failed"
    ]
    assert len(failure_records) == 1
    assert failure_records[0].exc_info is None
    serialized = OpenTelemetryJsonFormatter("test").format(failure_records[0])
    attributes = json.loads(serialized)["attributes"]
    assert attributes["exception.type"] == "ValidationError"
    assert attributes["method"] == "GET"
    assert attributes["status_code"] == 200
    assert attributes["normalized_route"] == "unmatched"
    assert "#metrics" not in serialized
    assert "exception.message" not in attributes


def test_metrics_failure_preserves_route_exception(caplog: pytest.LogCaptureFixture) -> None:
    class FailingRecorder:
        def record_completed_request(self, request: CompletedRestRequest) -> None:
            raise ValueError("metrics failed")

    with caplog.at_level("ERROR"):
        with pytest.raises(RuntimeError, match="route failed"):
            TestClient(create_test_app(FailingRecorder(), application_failures=create_application_failure_signal())).get("/exception")

    assert "REST metrics recording failed" in caplog.text


def test_records_5xx_and_preserves_route_exception() -> None:
    recorder = InMemoryRestMetricsRecorder()

    with pytest.raises(RuntimeError, match="route failed"):
        TestClient(create_test_app(recorder, application_failures=create_application_failure_signal())).get("/exception")

    assert recorder.metric_samples()[0].labels["status_class"] == "5xx"


def test_failing_failure_receivers_do_not_change_rest_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FailingRecorder:
        def record_completed_request(self, request: CompletedRestRequest) -> None:
            raise ValueError("secret-canary")

    calls: list[ApplicationFailure] = []

    def fail_logging(receiver: object, event: ApplicationFailure) -> None:
        calls.append(event)
        raise RuntimeError("logging failed")

    def fail_custom(event: ApplicationFailure) -> None:
        raise RuntimeError("custom receiver failed")

    monkeypatch.setattr("umbod.logging.ApplicationFailureLoggingReceiver.__call__", fail_logging)
    signal = create_application_failure_signal()
    failures = CapturingApplicationFailures()
    signal.connect("private-receiver", fail_custom)
    signal.connect("capture", failures.send)
    app = create_test_app(FailingRecorder(), application_failures=signal)

    response = TestClient(app).get("/items/alpha")

    assert response.status_code == 200
    assert response.json() == {"item_id": "alpha"}
    assert len(calls) == 3
    assert len(failures.events) == 1
    assert dict(failures.events[0].attributes)["status_code"] == 200
