from typing import Optional

import pytest
from fastapi import APIRouter, FastAPI, Request, Response
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from umbod.rest.authentication import AdminAuthenticationMiddleware
from umbod.rest.metrics import (
    AdminRestMetricsMiddleware,
    CompletedRestRequest,
    InMemoryRestMetricsRecorder,
    RestMetricsRecorder,
)


class RejectingAuthenticationStrategy:
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code

    async def authenticate(self, request: Request) -> Optional[Response]:
        return JSONResponse({"detail": "rejected"}, status_code=self.status_code)


def create_test_app(
    recorder: RestMetricsRecorder,
    authentication_status: Optional[int] = None,
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
    app.add_middleware(AdminRestMetricsMiddleware, recorder=recorder, routes=router.routes)
    return app


def test_records_completed_admin_responses_by_normalized_route_and_status_class() -> None:
    recorder = InMemoryRestMetricsRecorder()
    client = TestClient(create_test_app(recorder))

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
    app = create_test_app(recorder, status_code)

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
    admin_client = TestClient(create_test_app(recorder))
    root_app = FastAPI()

    @root_app.get("/system/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    assert admin_client.get("/unknown/private-user").status_code == 404
    assert TestClient(root_app).get("/system/health").status_code == 200
    assert recorder.metric_samples() == ()


def test_unknown_methods_use_bounded_other_label() -> None:
    recorder = InMemoryRestMetricsRecorder()

    response = TestClient(create_test_app(recorder)).request("CUSTOM", "/items/alpha")

    assert response.status_code == 405
    assert recorder.metric_samples()[0].labels["method"] == "OTHER"


def test_metrics_failure_preserves_response(caplog: pytest.LogCaptureFixture) -> None:
    class FailingRecorder:
        def record_completed_request(self, request: CompletedRestRequest) -> None:
            raise ValueError("metrics failed")

    with caplog.at_level("ERROR"):
        response = TestClient(create_test_app(FailingRecorder())).get("/items/alpha")

    assert response.status_code == 200
    assert response.json() == {"item_id": "alpha"}
    assert "REST metrics recording failed" in caplog.text


def test_metrics_model_validation_failure_preserves_response(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    def reject_request(**values: object) -> CompletedRestRequest:
        raise ValueError("invalid metrics model")

    monkeypatch.setattr(
        "umbod.rest.metrics.middleware.CompletedRestRequest",
        reject_request,
    )
    with caplog.at_level("ERROR"):
        response = TestClient(create_test_app(InMemoryRestMetricsRecorder())).get("/items/alpha")

    assert response.status_code == 200
    assert response.json() == {"item_id": "alpha"}
    assert "REST metrics recording failed" in caplog.text


def test_metrics_failure_preserves_route_exception(caplog: pytest.LogCaptureFixture) -> None:
    class FailingRecorder:
        def record_completed_request(self, request: CompletedRestRequest) -> None:
            raise ValueError("metrics failed")

    with caplog.at_level("ERROR"):
        with pytest.raises(RuntimeError, match="route failed"):
            TestClient(create_test_app(FailingRecorder())).get("/exception")

    assert "REST metrics recording failed" in caplog.text


def test_records_5xx_and_preserves_route_exception() -> None:
    recorder = InMemoryRestMetricsRecorder()

    with pytest.raises(RuntimeError, match="route failed"):
        TestClient(create_test_app(recorder)).get("/exception")

    assert recorder.metric_samples()[0].labels["status_class"] == "5xx"
