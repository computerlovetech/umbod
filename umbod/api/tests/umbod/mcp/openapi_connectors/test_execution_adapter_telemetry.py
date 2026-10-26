from umbod.mcp.listeners import create_mcp_signals
from umbod.mcp.signals import SignalToolExecutionPipelineFactory
import json
from types import SimpleNamespace
from typing import Any

import pytest

from umbod.core.capabilities import CapabilityIdentity
from umbod.core.invocation import PermitAllConnectorInvocationPolicy
from umbod.core.invocation.tools.execution import PreparedToolExecution, ToolExecutionPipeline, ToolExecutionRequest
from umbod.core.connectors.openapi.execution import (
    OpenApiCapabilityExecutionResult,
    OpenApiExecutionResponse,
)
from umbod.mcp.connectors.native.tools.deployment_modes.codemode import (
    OpenApiCodeModeInvocation,
)
from umbod.mcp.logging import (
    McpAuditEvent,
    McpAuditRecorder,
)
from umbod.mcp.logging.audit.formatting import StructuredMcpAuditFormatter
from umbod.mcp.logging.invocation.formatting import StructuredMcpToolInvocationLogFormatter
from umbod.mcp.logging.invocation.sink import InMemoryMcpToolInvocationLogSink
from umbod.mcp.metrics import InMemoryMcpMetricsRecorder
from umbod.mcp.metrics.in_memory import INVOCATION_COUNT_METRIC, INVOCATION_DURATION_COUNT_METRIC
from umbod.mcp.connectors.openapi import OpenApiCodeModeExecutionAdapter


class RecordingAuditSink:
    def __init__(self) -> None:
        self.events: list[McpAuditEvent] = []

    def record_mcp_activity(self, event: McpAuditEvent) -> None:
        self.events.append(event)


class ResourceFactory:
    def __init__(self, resource: object) -> None:
        self._resource = resource

    async def create(self) -> object:
        return self._resource


class SyncResourceFactory:
    def __init__(self, resource: object) -> None:
        self._resource = resource

    def create(self) -> object:
        return self._resource


class ConnectorStore:
    def __init__(
        self, display_name: str = "Weather", lookup_error: Exception | None = None
    ) -> None:
        self._display_name = display_name
        self._lookup_error = lookup_error

    async def get_connector(self, connector_id: str) -> object:
        if self._lookup_error is not None:
            raise self._lookup_error
        return SimpleNamespace(display_name=self._display_name)

    def close(self) -> None:
        return None


class ExecutionService:
    def __init__(
        self,
        result: OpenApiCapabilityExecutionResult,
        execution_pipeline: ToolExecutionPipeline[OpenApiExecutionResponse],
    ) -> None:
        self._result = result
        self._execution_pipeline = execution_pipeline
        self.executions = 0

    async def execute(
        self, operation_input: object, groups: tuple[str, ...]
    ) -> OpenApiCapabilityExecutionResult:
        self.executions += 1
        identity = CapabilityIdentity(
            connector_kind="openapi",
            connector_id="weather-id",
            capability_kind="tool",
            capability_key="forecast",
        )
        request = ToolExecutionRequest(
            identity=identity,
            public_tool_name="execute_openapi",
            arguments={},
        )

        async def prepare() -> PreparedToolExecution[OpenApiExecutionResponse]:
            async def operation() -> OpenApiExecutionResponse:
                if self._result.status == "error":
                    raise RuntimeError("outbound failed")
                return OpenApiExecutionResponse(
                    status=self._result.http_status if self._result.http_status is not None else 200,
                    content_type="application/json",
                    headers={},
                    body=self._result.message.encode(),
                    truncated=False,
                )

            return PreparedToolExecution(
                arguments={},
                operation=operation,
                invocation_arguments={},
            )

        try:
            await self._execution_pipeline.execute(request, prepare)
        except RuntimeError:
            return self._result
        return self._result


async def _execute(
    monkeypatch: pytest.MonkeyPatch,
    result: OpenApiCapabilityExecutionResult,
    store: ConnectorStore,
    secret: str = "secret-marker",
) -> tuple[dict[str, Any], InMemoryMcpToolInvocationLogSink, RecordingAuditSink, ExecutionService, InMemoryMcpMetricsRecorder]:
    invocation_sink = InMemoryMcpToolInvocationLogSink(StructuredMcpToolInvocationLogFormatter())
    audit_sink = RecordingAuditSink()
    server = SimpleNamespace(
        auth=None,
        openapi_connector_store_factory=ResourceFactory(store),
        group_permission_reader_factory=ResourceFactory(SimpleNamespace(close=lambda: None)),
        openapi_outbound_http_client_factory=SyncResourceFactory(
            SimpleNamespace(aclose=lambda: None)
        ),
        permission_group_claim="groups",
        connector_invocation_policy=PermitAllConnectorInvocationPolicy(),
        metrics_recorder=InMemoryMcpMetricsRecorder(),
    )
    service: ExecutionService | None = None

    async def _execution_service(*args: object) -> ExecutionService:
        nonlocal service
        execution_pipeline = args[-1]
        service = ExecutionService(result, execution_pipeline)
        return service

    monkeypatch.setattr(OpenApiCodeModeExecutionAdapter, "_execution_service", _execution_service)
    signals = create_mcp_signals(invocation_sink, server.metrics_recorder, McpAuditRecorder(audit_sink, "test"))
    adapter = OpenApiCodeModeExecutionAdapter(server, SignalToolExecutionPipelineFactory(signals, server.connector_invocation_policy))
    response = await adapter.execute(
        OpenApiCodeModeInvocation(
            connector_id="weather-id",
            operation_id="forecast",
            path={},
            query={"token": secret},
            headers={},
            body={"value": {"password": secret}},
        )
    )
    if service is None:
        raise RuntimeError("Execution service was not created")
    return response, invocation_sink, audit_sink, service, server.metrics_recorder


@pytest.mark.asyncio
async def test_execute_records_display_name_success(monkeypatch: pytest.MonkeyPatch) -> None:
    _, invocation_sink, audit_sink, _, _ = await _execute(
        monkeypatch,
        OpenApiCapabilityExecutionResult(status="success", message="done"),
        ConnectorStore("Weather API"),
    )

    assert invocation_sink.invocation_records()[0].attributes["mcp.connector.name"] == "Weather API"
    assert invocation_sink.invocation_records()[0].attributes["mcp.invocation.outcome"] == "success"
    assert audit_sink.events[0].target.connector_name == "Weather API"


@pytest.mark.asyncio
async def test_execute_records_pipeline_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    _, invocation_sink, _, _, _ = await _execute(
        monkeypatch,
        OpenApiCapabilityExecutionResult(status="error", code="outbound_failed", message="failed"),
        ConnectorStore(),
    )

    assert invocation_sink.invocation_records()[0].attributes["mcp.invocation.outcome"] == "failure"


@pytest.mark.asyncio
async def test_execute_uses_id_when_metadata_lookup_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    _, invocation_sink, _, service, _ = await _execute(
        monkeypatch,
        OpenApiCapabilityExecutionResult(status="success", message="done"),
        ConnectorStore(lookup_error=RuntimeError("lookup failed")),
    )

    assert service.executions == 1
    assert invocation_sink.invocation_records()[0].attributes["mcp.connector.name"] == "weather-id"


@pytest.mark.asyncio
async def test_execute_telemetry_excludes_input_and_result_secrets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret = "never-serialize-this"
    _, invocation_sink, audit_sink, _, _ = await _execute(
        monkeypatch,
        OpenApiCapabilityExecutionResult(status="success", message=secret),
        ConnectorStore(),
        secret,
    )

    invocation_payload = json.dumps(invocation_sink.invocation_records()[0].attributes)
    audit_payload = json.dumps(
        StructuredMcpAuditFormatter().format_mcp_activity(audit_sink.events[0]).attributes
    )
    assert secret not in invocation_payload
    assert secret not in audit_payload


@pytest.mark.asyncio
@pytest.mark.parametrize("http_status", [200, 302, 400, 401, 404, 500, 503])
async def test_execute_classifies_http_status_for_telemetry_without_changing_transport_result(
    monkeypatch: pytest.MonkeyPatch,
    http_status: int,
) -> None:
    secret = "response-body-secret"
    result = OpenApiCapabilityExecutionResult(
        status="success", message=secret, http_status=http_status
    )
    response, invocation_sink, audit_sink, service, metrics = await _execute(
        monkeypatch, result, ConnectorStore(), secret
    )

    assert response == result.model_dump(mode="json")
    assert service.executions == 1
    records = invocation_sink.invocation_records()
    assert len(records) == 1
    attributes = records[0].attributes
    outcome = "failure" if http_status >= 400 else "success"
    assert attributes["mcp.invocation.outcome"] == outcome
    if http_status >= 400:
        assert attributes["mcp.failure.origin"] == "downstream_openapi"
        assert "exception.type" not in attributes
        assert "exception.stacktrace" not in attributes
    else:
        assert "mcp.failure.origin" not in attributes
    all_samples = metrics.metric_samples()
    assert len(all_samples) == 4
    samples = tuple(sample for sample in all_samples if sample.value > 0)
    assert len(samples) == 2
    assert {sample.name for sample in samples} == {
        INVOCATION_COUNT_METRIC, INVOCATION_DURATION_COUNT_METRIC
    }
    for sample in samples:
        assert sample.value == 1
        assert sample.labels == {
            "connector_name": "weather-id",
            "tool_name": "execute_openapi",
            "outcome": outcome,
        }
    assert len(audit_sink.events) == 1
    audit_attributes = StructuredMcpAuditFormatter().format_mcp_activity(
        audit_sink.events[0]
    ).attributes
    assert secret not in json.dumps(attributes)
    assert secret not in json.dumps(audit_attributes)
    assert secret not in json.dumps([sample.model_dump(mode="json") for sample in samples])
