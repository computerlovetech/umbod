from collections.abc import Iterator

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from prometheus_client import CONTENT_TYPE_LATEST
from prometheus_client.parser import text_string_to_metric_families
from prometheus_client.samples import Sample

from umbod.rest.metrics import (
    AdminRestMetricsMiddleware,
    PrometheusRestMetricsRecorder,
    create_rest_metrics_app,
)


@pytest.fixture
def metrics_clients() -> Iterator[tuple[TestClient, TestClient]]:
    recorder = PrometheusRestMetricsRecorder()
    router = APIRouter()

    @router.get("/items/{item_id}")
    async def read_item(item_id: str) -> JSONResponse:
        return JSONResponse({"item_id": item_id}, status_code=500 if item_id == "error" else 200)

    @router.post("/items/{item_id}")
    async def create_item(item_id: str) -> JSONResponse:
        return JSONResponse({"item_id": item_id}, status_code=201)

    app = FastAPI()
    app.include_router(router)

    @app.get("/system/health")
    @app.get("/oauth/callback")
    async def non_admin_route() -> dict[str, str]:
        return {"status": "ok"}

    app.add_middleware(AdminRestMetricsMiddleware, recorder=recorder, routes=router.routes)
    with TestClient(app) as traffic, TestClient(create_rest_metrics_app(recorder)) as metrics:
        yield traffic, metrics


def _samples(client: TestClient) -> tuple[Sample, ...]:
    response = client.get("/metrics")
    assert response.status_code == 200
    assert response.headers["content-type"] == CONTENT_TYPE_LATEST
    return tuple(
        sample
        for family in text_string_to_metric_families(response.text)
        for sample in family.samples
    )


def test_completed_http_requests_are_scraped_with_normalized_bounded_labels(
    metrics_clients: tuple[TestClient, TestClient],
) -> None:
    traffic, metrics = metrics_clients
    assert traffic.get("/items/private-user?token=secret-canary").status_code == 200
    assert traffic.get("/items/another-user").status_code == 200
    assert traffic.post("/items/private-user").status_code == 201
    assert traffic.get("/items/error").status_code == 500

    samples = _samples(metrics)
    expected_counts = {("GET", "2xx"): 2, ("POST", "2xx"): 1, ("GET", "5xx"): 1}
    for metric_name in (
        "umbod_rest_requests_total",
        "umbod_rest_request_duration_seconds_count",
    ):
        actual = {
            (sample.labels["method"], sample.labels["status_class"]): sample.value
            for sample in samples
            if sample.name == metric_name
        }
        assert actual == expected_counts
        assert all(
            sample.labels
            == {
                "method": sample.labels["method"],
                "route": "/admin/items/{item_id}",
                "status_class": sample.labels["status_class"],
            }
            for sample in samples
            if sample.name == metric_name
        )
    duration_sums = {
        (sample.labels["method"], sample.labels["status_class"]): sample.value
        for sample in samples
        if sample.name == "umbod_rest_request_duration_seconds_sum"
    }
    assert duration_sums.keys() == expected_counts.keys()
    assert all(value > 0 for value in duration_sums.values())
    assert "private-user" not in str(samples)
    assert "another-user" not in str(samples)
    assert "secret-canary" not in str(samples)


def test_unmatched_and_non_admin_http_requests_do_not_create_metric_series(
    metrics_clients: tuple[TestClient, TestClient],
) -> None:
    traffic, metrics = metrics_clients
    assert traffic.get("/missing/private-user").status_code == 404
    assert traffic.get("/system/health").status_code == 200
    assert traffic.get("/oauth/callback").status_code == 200

    assert not any(sample.name.startswith("umbod_rest_") for sample in _samples(metrics))
