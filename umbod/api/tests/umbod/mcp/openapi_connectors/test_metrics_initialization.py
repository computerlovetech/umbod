from typing import cast
from unittest.mock import create_autospec

import pytest

from umbod.core.connectors.openapi.management.models import OpenApiConnector
from umbod.core.connectors.openapi.stores import OpenApiConnectorReader
from umbod.mcp.connectors.openapi.inventory import read_openapi_tool_inventory
from tests.umbod.mcp.downstream_mcp_connectors.signal_support import invocation_signals
from umbod.mcp.metrics import InMemoryMcpMetricsRecorder, McpMetricsRecorder


@pytest.fixture
def connector_reader() -> OpenApiConnectorReader:
    connector = OpenApiConnector(
        connector_id="weather", display_name="Weather", tool_name_prefix="weather",
        capability_description="Weather forecasts", created_at="2026-01-01", updated_at="2026-01-01",
    )
    reader = create_autospec(OpenApiConnectorReader, instance=True)
    reader.list_connectors.return_value = (connector,)
    return cast(OpenApiConnectorReader, reader)


@pytest.mark.asyncio
async def test_known_openapi_inventory_initializes_both_outcomes_without_completions(
    connector_reader: OpenApiConnectorReader,
) -> None:
    recorder = InMemoryMcpMetricsRecorder()
    port: McpMetricsRecorder = recorder

    signals = invocation_signals(port)
    event = await read_openapi_tool_inventory(connector_reader)
    assert [(identity.tool_name, identity.connector_id, identity.connector_name, identity.operation_name) for identity in event.identities] == [("execute_openapi", "weather", "Weather", None)]
    signals.tool_inventory_observed.send(event)
    signals.tool_inventory_observed.send(event)

    samples = recorder.metric_samples()
    assert len(samples) == 4
    assert all(sample.value == 0 for sample in samples)
    assert {sample.labels["outcome"] for sample in samples} == {"success", "failure"}
    assert all(sample.labels["connector_name"] == "weather" for sample in samples)
    assert all(sample.labels["tool_name"] == "execute_openapi" for sample in samples)


@pytest.mark.asyncio
async def test_metrics_initialization_failure_does_not_abort_openapi_inventory_setup(
    connector_reader: OpenApiConnectorReader, caplog: pytest.LogCaptureFixture,
) -> None:
    recorder = create_autospec(McpMetricsRecorder, instance=True)
    recorder.initialize_invocation.side_effect = RuntimeError("private-initialization-detail")

    signals = invocation_signals(cast(McpMetricsRecorder, recorder))
    signals.tool_inventory_observed.send(await read_openapi_tool_inventory(connector_reader))

    recorder.initialize_invocation.assert_called_once()
    recorder.record_completed_invocation.assert_not_called()
    assert "mcp.inventory.metrics" in caplog.text
    assert "private-initialization-detail" not in caplog.text
