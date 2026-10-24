from collections.abc import Iterator

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from prometheus_client import CONTENT_TYPE_LATEST
from prometheus_client.parser import text_string_to_metric_families
from prometheus_client.samples import Sample

from umbod.rest.factories import SubApiAppFactory
from umbod.rest.metrics import (
    AdminRestMetricsMiddleware,
    PrometheusRestMetricsRecorder,
    create_rest_metrics_app,
)


@pytest.fixture(params=[0, 1, 2], ids=["leaf-router", "included-router", "nested-included-router"])
def metrics_clients(request: pytest.FixtureRequest) -> Iterator[tuple[TestClient, TestClient]]:
    recorder = PrometheusRestMetricsRecorder()
    router = APIRouter(prefix="/connectors" if request.param == 0 else "")

    @router.get("/catalog")
    async def catalog() -> dict[str, str]:
        return {"status": "ok"}

    @router.get("/items/{item_id}")
    async def read_item(item_id: str) -> JSONResponse:
        return JSONResponse({"item_id": item_id}, status_code=500 if item_id == "error" else 200)

    @router.post("/items/{item_id}")
    async def create_item(item_id: str) -> JSONResponse:
        return JSONResponse({"item_id": item_id}, status_code=201)

    for depth in range(request.param):
        parent_router = APIRouter()
        parent_router.include_router(router, prefix="/connectors" if depth == 0 else "")
        router = parent_router

    admin_app = SubApiAppFactory(title="metrics-acceptance", router=router).create()
    admin_app.add_middleware(
        AdminRestMetricsMiddleware, recorder=recorder, routes=tuple(router.routes)
    )
    app = FastAPI()
    app.mount("/api/admin", admin_app)

    @app.get("/system/health")
    @app.get("/oauth/callback")
    async def non_admin_route() -> dict[str, str]:
        return {"status": "ok"}

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
    assert traffic.get("/api/admin/connectors/items/private-user?token=secret-canary").status_code == 200
    assert traffic.get("/api/admin/connectors/items/another-user").status_code == 200
    assert traffic.post("/api/admin/connectors/items/private-user").status_code == 201
    assert traffic.get("/api/admin/connectors/items/error").status_code == 500

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
                "route": "/admin/connectors/items/{item_id}",
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


def test_successful_connector_catalog_request_creates_scrapable_metrics(
    metrics_clients: tuple[TestClient, TestClient],
) -> None:
    traffic, metrics = metrics_clients

    response = traffic.get("/api/admin/connectors/catalog")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    samples = _samples(metrics)
    for metric_name in (
        "umbod_rest_requests_total",
        "umbod_rest_request_duration_seconds_count",
    ):
        matching_samples = [sample for sample in samples if sample.name == metric_name]
        assert len(matching_samples) == 1
        assert matching_samples[0].value == 1
        assert matching_samples[0].labels == {
            "method": "GET",
            "route": "/admin/connectors/catalog",
            "status_class": "2xx",
        }


def test_method_not_allowed_for_connector_catalog_is_recorded(
    metrics_clients: tuple[TestClient, TestClient],
) -> None:
    traffic, metrics = metrics_clients

    assert traffic.post("/api/admin/connectors/catalog").status_code == 405

    counts = [sample for sample in _samples(metrics) if sample.name == "umbod_rest_requests_total"]
    assert len(counts) == 1
    assert counts[0].value == 1
    assert counts[0].labels == {
        "method": "POST",
        "route": "/admin/connectors/catalog",
        "status_class": "4xx",
    }


def test_unmatched_and_non_admin_http_requests_do_not_create_metric_series(
    metrics_clients: tuple[TestClient, TestClient],
) -> None:
    traffic, metrics = metrics_clients
    assert traffic.get("/api/admin/connectors/missing/private-user").status_code == 404
    assert traffic.get("/system/health").status_code == 200
    assert traffic.get("/oauth/callback").status_code == 200

    assert not any(sample.name.startswith("umbod_rest_") for sample in _samples(metrics))
