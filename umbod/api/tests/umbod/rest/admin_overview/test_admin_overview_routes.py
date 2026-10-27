from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.routing import Mount

from umbod.core.admin_overview import AdminOverviewService
from umbod.core.admin_overview.models import AdminOverview, Available, OverviewSnapshot, ToolCounts
from umbod.rest.admin_overview.dependencies import get_admin_overview_service
from umbod.rest.main import create_app
from umbod.rest.settings import APISettings


@pytest.fixture(params=["inmemory", "sqlite"])
def client(request: pytest.FixtureRequest, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    availability = tmp_path / "availability.json"
    availability.write_text('{"connectors": []}', encoding="utf-8")
    monkeypatch.setenv("UMBOD_CONNECTOR_DEPLOYMENT_CONFIGURATION_PATH", str(availability))
    settings = APISettings(
        admin_authentication={"mode": "simulation", "simulated_admin": True},
        connector_store={"type": request.param, "sqlite_path": str(tmp_path / "overview.sqlite3")},
        rest={"metrics_enabled": False},
    )
    with TestClient(
        create_app(settings=settings, connector_registrations=[]), raise_server_exceptions=False,
    ) as transport:
        yield transport


def test_empty_overview_has_available_zero_counts_and_no_store(client: TestClient) -> None:
    response = client.get("/api/admin/overview")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    summary = AdminOverview.model_validate(response.json())
    assert summary.configured == Available(status="available", value=0)
    assert summary.published == Available(status="available", value=0)
    assert summary.tools == Available(status="available", value=ToolCounts(enabled=0, known=0))
    assert summary.permission_groups == Available(status="available", value=0)
    assert tuple(row.kind for row in summary.breakdown) == ("catalog", "openapi", "mcp")


def test_overview_reads_fresh_group_count_without_returning_group_identifiers(client: TestClient) -> None:
    group_id = "summary-group-private-identifier"
    before = client.get("/api/admin/overview")
    assert before.json()["permission_groups"] == {"status": "available", "value": 0}
    assert client.post("/api/admin/groups", json={"group_id": group_id}).status_code == 204
    after = client.get("/api/admin/overview")
    assert after.status_code == 200
    assert after.json()["permission_groups"] == {"status": "available", "value": 1}
    assert group_id not in after.text


class UnavailableReader:
    async def read(self) -> OverviewSnapshot:
        raise RuntimeError("database unavailable")


def test_database_failure_does_not_serialize_zero_counts(client: TestClient) -> None:
    def unavailable_service() -> AdminOverviewService:
        return AdminOverviewService(UnavailableReader())

    assert isinstance(client.app, FastAPI)
    admin = next(route.app for route in client.app.routes if isinstance(route, Mount) and route.path == "/api/admin")
    assert isinstance(admin, FastAPI)
    admin.dependency_overrides[get_admin_overview_service] = unavailable_service
    response = client.get("/api/admin/overview")
    assert response.status_code == 500
    assert "database unavailable" not in response.text
    assert '"value":0' not in response.text
