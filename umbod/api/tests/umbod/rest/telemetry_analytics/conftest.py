from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.routing import Mount

from umbod.config import AppConfig
from umbod.core.telemetry.analytics import LogCountQuery, LogCountResult, LogDimension, TelemetryAnalyticsReader
from umbod.rest.authentication.authorization import JwtClaims, JwtVerificationError
from umbod.rest.main import create_app
from umbod.rest.telemetry.dependencies import get_analytics_reader

from tests.umbod.core.telemetry.analytics.in_memory import InMemoryTelemetryAnalyticsReader, NormalizedLog


class AnalyticsVerifier:
    def verify(self, token: str) -> JwtClaims:
        if token not in {"admin", "member"}:
            raise JwtVerificationError("Invalid analytics test credentials")
        return JwtClaims(claims={
            "iss": "test:analytics", "sub": token,
            "groups": ["analytics-admins"] if token == "admin" else ["members"],
        })


class RecordingReader:
    def __init__(self, reader: TelemetryAnalyticsReader) -> None:
        self.reader = reader
        self.queries: list[LogCountQuery] = []

    async def count_logs(self, query: LogCountQuery) -> LogCountResult:
        self.queries.append(query)
        return await self.reader.count_logs(query)


@dataclass(frozen=True)
class AnalyticsHttp:
    client: TestClient
    admin: FastAPI
    reader: RecordingReader


@pytest.fixture
def configuration(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AppConfig:
    deployment = tmp_path / "deployment.json"
    deployment.write_text('{"connectors": []}', encoding="utf-8")
    monkeypatch.setenv("UMBOD_CONNECTOR_DEPLOYMENT_CONFIGURATION_PATH", str(deployment))
    return AppConfig(
        admin_authentication={
            "mode": "jwt", "environment": "development", "required_membership": "analytics-admins",
        },
        rest={"metrics_enabled": False},
    )


@pytest.fixture
def query_body() -> dict[str, object]:
    return {
        "time_range": {"start": "2026-01-01T00:00:00Z", "end": "2026-01-02T00:00:00Z"},
        "filters": [], "group_by": [], "bucketing": {"kind": "none"}, "max_groups": 100,
    }


@pytest.fixture
def reader() -> RecordingReader:
    logs = (
        NormalizedLog(
            occurred_at=datetime(2026, 1, 1, 0, 10, tzinfo=timezone.utc), owner_id=None,
            dimensions={
                LogDimension.SOURCE: "codex", LogDimension.EVENT_NAME: "tool_result",
                LogDimension.SEVERITY: "INFO", LogDimension.TOOL_NAME: "",
            },
        ),
        NormalizedLog(
            occurred_at=datetime(2026, 1, 1, 0, 20, tzinfo=timezone.utc), owner_id=None,
            dimensions={
                LogDimension.SOURCE: "codex", LogDimension.EVENT_NAME: "tool_result",
                LogDimension.SEVERITY: "ERROR", LogDimension.TOOL_NAME: "shell",
            },
        ),
        NormalizedLog(
            occurred_at=datetime(2026, 1, 1, 1, 0, tzinfo=timezone.utc), owner_id="member",
            dimensions={LogDimension.SOURCE: "claude-code", LogDimension.EVENT_NAME: "user_prompt"},
        ),
    )
    return RecordingReader(InMemoryTelemetryAnalyticsReader(logs))


@pytest.fixture
def analytics_http(configuration: AppConfig, reader: RecordingReader) -> Iterator[AnalyticsHttp]:
    root = create_app(configuration, (), admin_verifier=AnalyticsVerifier())
    admin = next(route.app for route in root.routes if isinstance(route, Mount) and route.path == "/api/admin")
    assert isinstance(admin, FastAPI)

    def provide_reader() -> TelemetryAnalyticsReader:
        return reader

    admin.dependency_overrides[get_analytics_reader] = provide_reader
    with TestClient(root, headers={"Authorization": "Bearer admin"}, raise_server_exceptions=False) as client:
        yield AnalyticsHttp(client=client, admin=admin, reader=reader)
