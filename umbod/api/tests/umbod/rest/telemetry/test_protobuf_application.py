from datetime import datetime, timezone

import httpx
import pytest
from opentelemetry.proto.collector.logs.v1.logs_service_pb2 import (
    ExportLogsServiceRequest,
)

from umbod.config import AppConfig, OtlpReceiverConfig, RuntimeConfig, TelemetryAnalyticsConfig
from umbod.config.telemetry import TelemetryAppConfig
from umbod.core.telemetry import TelemetryExport, TelemetrySink
from umbod.core.telemetry.analytics import (
    InstanceScope,
    LogCountQuery,
    LogDimension,
    NoTimeBuckets,
    TelemetryAnalyticsRuntime,
    TelemetryAnalyticsUnavailable,
    TimeRange,
)
from umbod.rest.telemetry import application as telemetry_application
from umbod.rest.telemetry.application import create_telemetry_app
from umbod.rest.telemetry.dependencies import get_analytics_reader, get_telemetry_sink

from tests.persistence_runtime import create_inmemory_runtime
from tests.support.telemetry_runtime import InMemoryTelemetryAnalyticsRuntime


class RecordingSink:
    def __init__(self) -> None:
        self.batches: list[TelemetryExport] = []

    def export(self, batch: TelemetryExport) -> None:
        self.batches.append(batch)


@pytest.mark.anyio
async def test_standalone_collector_retains_protobuf_logs_across_application_reconstruction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = TelemetryAppConfig(
        runtime=RuntimeConfig(profile="production"),
        otlp_receiver=OtlpReceiverConfig(enabled=True, bearer_token="collector-token"),
        telemetry_analytics=TelemetryAnalyticsConfig(enabled=False),
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
    persistence = create_inmemory_runtime()
    selected_settings: list[AppConfig | TelemetryAppConfig] = []

    def select_runtime(config: AppConfig | TelemetryAppConfig) -> TelemetryAnalyticsRuntime:
        selected_settings.append(config)
        return InMemoryTelemetryAnalyticsRuntime(persistence.database, persistence.readiness)

    sink = RecordingSink()

    def provide_sink() -> TelemetrySink:
        return sink

    try:
        monkeypatch.setattr(telemetry_application, "create_configured_analytics_runtime", select_runtime)
        app = create_telemetry_app(settings)
        app.dependency_overrides[get_telemetry_sink] = provide_sink
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://collector") as client:
                response = await client.post(
                    "/v1/logs",
                    content=request.SerializeToString(),
                    headers={
                        "Content-Type": "application/x-protobuf",
                        "Authorization": "Bearer collector-token",
                    },
                )
                assert response.status_code == 200
                assert response.content == b""
                assert response.headers["content-type"] == "application/x-protobuf"
                assert len(sink.batches) == 1
                assert sink.batches[0].item_count == 1
                previous_reader = app.dependency_overrides[get_analytics_reader]()
        recreated = create_telemetry_app(settings)
        async with recreated.router.lifespan_context(recreated):
            with pytest.raises(TelemetryAnalyticsUnavailable):
                await previous_reader.count_logs(query)
            reader = recreated.dependency_overrides[get_analytics_reader]()
            result = await reader.count_logs(query)
            assert len(result.rows) == 1
            assert result.rows[0].count == 1
            assert tuple(group.value.value for group in result.rows[0].groups) == (
                "hermes-agent",
                "tool.completed",
                "session-1",
                "shell",
            )
            assert reader is not previous_reader
        assert len(selected_settings) == 2
        assert all(config is settings for config in selected_settings)
    finally:
        await persistence.shutdown()
