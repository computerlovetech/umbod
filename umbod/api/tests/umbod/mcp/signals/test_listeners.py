from unittest.mock import Mock

import pytest

from umbod.core.signals import InMemorySignalFailureHandler
from umbod.mcp.listeners import create_mcp_signals, register_mcp_listeners
from umbod.mcp.logging import McpAuditRecorder, McpToolInvocationLogSink
from umbod.mcp.metrics import InvocationScope, McpMetricsRecorder
from umbod.mcp.metrics.in_memory import InMemoryMcpMetricsRecorder
from umbod.mcp.signals import McpInvocationPublisher, McpSignals, McpToolIdentity, McpToolInvocationCompleted, ToolInventoryObserved


@pytest.fixture
def ports() -> tuple[Mock, Mock, Mock]:
    return Mock(spec=McpToolInvocationLogSink), Mock(spec=McpMetricsRecorder), Mock(spec=McpAuditRecorder)


def test_custom_receiver_receives_same_immutable_completion_as_log_sink(ports: tuple[Mock, Mock, Mock]) -> None:
    log, metrics, audit = ports
    signals = create_mcp_signals(log, metrics, audit)
    observed: list[McpToolInvocationCompleted] = []
    signals.invocation_completed.connect("custom", observed.append)
    publisher = McpInvocationPublisher(signals)
    lifecycle = publisher.start(McpToolIdentity("tool", "connector", "operation"))
    publisher.succeeded(lifecycle)
    publisher.succeeded(lifecycle)
    assert len(observed) == 1
    assert log.record_invocation_completed.call_args.args[0] is observed[0]


@pytest.mark.parametrize("failed_receiver", ["logging", "metrics", "audit"])
def test_receiver_failure_does_not_prevent_other_delivery(ports: tuple[Mock, Mock, Mock], failed_receiver: str) -> None:
    log, metrics, audit = ports
    methods = {
        "logging": log.record_invocation_completed,
        "metrics": metrics.record_completed_invocation,
        "audit": audit.record_tool_invocation,
    }
    methods[failed_receiver].side_effect = RuntimeError("failure")
    signals = create_mcp_signals(log, metrics, audit)
    publisher = McpInvocationPublisher(signals)
    publisher.succeeded(publisher.start(McpToolIdentity("tool", "connector", "operation")))
    for method in methods.values():
        method.assert_called_once()


def test_app_signal_receivers_are_isolated(ports: tuple[Mock, Mock, Mock]) -> None:
    first = create_mcp_signals(*ports)
    other_ports = tuple(Mock(spec=port_type) for port_type in (McpToolInvocationLogSink, McpMetricsRecorder, McpAuditRecorder))
    second = create_mcp_signals(*other_ports)
    first.tool_inventory_observed.send(ToolInventoryObserved((McpToolIdentity("tool", None, None),)))
    ports[1].initialize_invocation.assert_called_once()
    other_ports[1].initialize_invocation.assert_not_called()
    assert first is not second


def test_inventory_repeated_observations_initialize_zero_series_without_completion(ports: tuple[Mock, Mock, Mock]) -> None:
    log, _, audit = ports
    recorder = InMemoryMcpMetricsRecorder()
    metrics: McpMetricsRecorder = recorder
    signals = create_mcp_signals(log, metrics, audit)
    publisher = McpInvocationPublisher(signals)
    identity = McpToolIdentity("tool", "connector", "operation")
    publisher.tool_registered(identity)
    publisher.tool_registered(identity)
    samples = recorder.metric_samples()
    assert len(samples) == 4
    assert {sample.labels["outcome"] for sample in samples} == {"success", "failure"}
    assert all(sample.value == 0 for sample in samples)
    log.record_invocation_completed.assert_not_called()
    audit.record_tool_invocation.assert_not_called()


def test_inventory_failure_does_not_skip_remaining_identities(ports: tuple[Mock, Mock, Mock]) -> None:
    log, metrics, audit = ports
    metrics.initialize_invocation.side_effect = [RuntimeError("failure"), None]
    signals = create_mcp_signals(log, metrics, audit)
    signals.tool_inventory_observed.send(ToolInventoryObserved((McpToolIdentity("first", None, None), McpToolIdentity("second", None, None))))
    assert metrics.initialize_invocation.call_count == 2


@pytest.mark.parametrize("connector_id,scope", [(None, InvocationScope.REQUEST), ("connector", InvocationScope.CONNECTOR)])
def test_completion_metrics_preserve_scope(ports: tuple[Mock, Mock, Mock], connector_id: str | None, scope: InvocationScope) -> None:
    publisher = McpInvocationPublisher(create_mcp_signals(*ports))
    publisher.succeeded(publisher.start(McpToolIdentity("tool", connector_id, None)))
    assert ports[1].record_completed_invocation.call_args.args[0].scope == scope


@pytest.mark.parametrize("tool_name,connector_id,audits", [("search_tools", None, 0), ("execute_tool", None, 0), ("execute_code", None, 0), ("other", None, 1), ("execute_code", "connector", 1)])
def test_audit_completion_ownership(ports: tuple[Mock, Mock, Mock], tool_name: str, connector_id: str | None, audits: int) -> None:
    publisher = McpInvocationPublisher(create_mcp_signals(*ports))
    publisher.succeeded(publisher.start(McpToolIdentity(tool_name, connector_id, None)))
    assert ports[2].record_tool_invocation.call_count == audits


@pytest.mark.parametrize("channel_name,receiver_name", (
    ("invocation_completed", "mcp.invocation.logging"),
    ("invocation_completed", "mcp.invocation.metrics"),
    ("invocation_completed", "mcp.invocation.audit"),
    ("tool_inventory_observed", "mcp.inventory.metrics"),
))
def test_registration_conflict_does_not_install_partial_side_effects(
    ports: tuple[Mock, Mock, Mock], channel_name: str, receiver_name: str,
) -> None:
    signals = McpSignals(InMemorySignalFailureHandler())

    def existing_receiver(event: object) -> None:
        return None

    getattr(signals, channel_name).connect(receiver_name, existing_receiver)
    with pytest.raises(ValueError):
        register_mcp_listeners(signals, *ports)

    publisher = McpInvocationPublisher(signals)
    publisher.succeeded(publisher.start(McpToolIdentity("tool", "connector", "operation")))
    ports[0].record_invocation_completed.assert_not_called()
    ports[1].record_completed_invocation.assert_not_called()
    ports[2].record_tool_invocation.assert_not_called()
    assert signals.invocation_completed.is_connected("mcp.invocation.logging") == (receiver_name == "mcp.invocation.logging")
    assert signals.invocation_completed.is_connected("mcp.invocation.metrics") == (receiver_name == "mcp.invocation.metrics")
    assert signals.invocation_completed.is_connected("mcp.invocation.audit") == (receiver_name == "mcp.invocation.audit")


def test_duplicate_registration_is_rejected_without_duplicate_delivery(ports: tuple[Mock, Mock, Mock]) -> None:
    signals = McpSignals(InMemorySignalFailureHandler())
    register_mcp_listeners(signals, *ports)
    with pytest.raises(ValueError):
        register_mcp_listeners(signals, *ports)
    publisher = McpInvocationPublisher(signals)
    publisher.succeeded(publisher.start(McpToolIdentity("tool", None, None)))
    ports[0].record_invocation_completed.assert_called_once()
