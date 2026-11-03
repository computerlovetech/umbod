from datetime import datetime, timezone
from pathlib import Path

from fastapi.testclient import TestClient
from opentelemetry.proto.collector.logs.v1.logs_service_pb2 import (
    ExportLogsServiceRequest,
)

from umbod.config import OtlpReceiverConfig, RuntimeConfig, TelemetryAnalyticsConfig
from umbod.config.telemetry import TelemetryAppConfig
from umbod.core.telemetry import TelemetryExport, TelemetrySink
from umbod.core.telemetry.analytics import (
    InstanceScope,
    LogCountQuery,
    LogDimension,
    NoTimeBuckets,
    TimeRange,
)
from umbod.rest.telemetry.application import create_telemetry_app
from umbod.rest.telemetry.dependencies import get_analytics_reader, get_telemetry_sink


class AcceptingSink:
    def export(self, batch: TelemetryExport) -> None:
        pass


def test_standalone_collector_persists_protobuf_logs_across_restart(
    tmp_path: Path,
) -> None:
    settings = TelemetryAppConfig(
        runtime=RuntimeConfig(profile="production"),
        otlp_receiver=OtlpReceiverConfig(enabled=True, bearer_token="collector-token"),
        telemetry_analytics=TelemetryAnalyticsConfig(
            enabled=True,
            sqlite_path=str(tmp_path / "analytics.sqlite3"),
        ),
    )
    request = ExportLogsServiceRequest(
        resource_logs=[
            {
                "resource": {
                    "attributes": [
                        {
                            "key": "service.name",
                            "value": {"string_value": "hermes-agent"},
                        },
                    ]
                },
                "scope_logs": [
                    {
                        "log_records": [
                            {
                                "event_name": "tool.completed",
                                "time_unix_nano": 1767226200000000000,
                                "trace_id": b"\xab" * 16,
                                "span_id": b"\xcd" * 8,
                                "attributes": [
                                    {
                                        "key": "session.id",
                                        "value": {"string_value": "session-1"},
                                    },
                                    {
                                        "key": "tool.name",
                                        "value": {"string_value": "shell"},
                                    },
                                ],
                            }
                        ]
                    }
                ],
            }
        ]
    )
    app = create_telemetry_app(settings)

    def provide_sink() -> TelemetrySink:
        return AcceptingSink()

    app.dependency_overrides[get_telemetry_sink] = provide_sink
    with TestClient(app) as client:
        response = client.post(
            "/v1/logs",
            content=request.SerializeToString(),
            headers={
                "Content-Type": "application/x-protobuf",
                "Authorization": "Bearer collector-token",
            },
        )
        assert response.status_code == 200
        assert response.content == b""
    restarted = create_telemetry_app(settings)
    query = LogCountQuery(
        scope=InstanceScope(kind="instance"),
        time_range=TimeRange(
            start=datetime(2026, 1, 1, tzinfo=timezone.utc),
            end=datetime(2026, 1, 2, tzinfo=timezone.utc),
        ),
        filters=(),
        group_by=(
            LogDimension.SOURCE,
            LogDimension.EVENT_NAME,
            LogDimension.SESSION_ID,
            LogDimension.TOOL_NAME,
        ),
        bucketing=NoTimeBuckets(kind="none"),
        max_groups=10,
    )
    with TestClient(restarted) as client:
        reader = restarted.dependency_overrides[get_analytics_reader]()
        result = client.portal.call(reader.count_logs, query)
        assert len(result.rows) == 1
        assert result.rows[0].count == 1
        assert tuple(group.value.value for group in result.rows[0].groups) == (
            "hermes-agent",
            "tool.completed",
            "session-1",
            "shell",
        )
