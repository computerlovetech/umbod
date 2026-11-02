from dataclasses import FrozenInstanceError
from unittest.mock import Mock

import pytest

from tests.support.application_failures import CapturingApplicationFailures
from tests.support.signals import InMemorySignalFailureHandler
from umbod.core.diagnostics import PublishingSignalFailureHandler
from umbod.core.invocation.failure_evidence import InvocationFailureOrigin, InvocationReturnedFailure
from umbod.mcp.signals import McpInvocationPublisher, McpSignals, McpToolIdentity, McpToolInvocationCompleted, McpToolInvocationFailureCategory
from umbod.mcp.signals.lifecycle import McpToolInvocationLifecycle, UnavailableToolInvocationLifecycle


def test_unavailable_lifecycle_is_immutable() -> None:
    lifecycle = UnavailableToolInvocationLifecycle()

    with pytest.raises(FrozenInstanceError):
        setattr(lifecycle, "__dataclass_fields__", {})


def test_unavailable_completion_publishes_no_invocation() -> None:
    signals = McpSignals(InMemorySignalFailureHandler())
    events: list[McpToolInvocationCompleted] = []
    signals.invocation_completed.connect("capture", events.append)
    publisher = McpInvocationPublisher(signals)
    lifecycle = UnavailableToolInvocationLifecycle()

    publisher.succeeded(lifecycle)
    publisher.failed(lifecycle, McpToolInvocationFailureCategory.UNEXPECTED_ERROR, None, InvocationReturnedFailure(InvocationFailureOrigin.INTERNAL))
    publisher.succeeded(lifecycle)

    assert events == []


def test_start_failure_returns_unavailable_and_reports_sanitized_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    failures = CapturingApplicationFailures()
    publisher = McpInvocationPublisher(McpSignals(PublishingSignalFailureHandler(failures)))
    monkeypatch.setattr(McpToolInvocationLifecycle, "start", Mock(side_effect=RuntimeError("private-start-token")))

    lifecycle = publisher.start(McpToolIdentity("tool", None, None))

    assert isinstance(lifecycle, UnavailableToolInvocationLifecycle)
    assert len(failures.events) == 1
    assert dict(failures.events[0].attributes)["exception.type"] == "RuntimeError"
    assert "private-start-token" not in failures.events[0].model_dump_json()


@pytest.mark.parametrize("first_completion", ["success", "failure"])
def test_active_lifecycle_suppresses_duplicate_mixed_completions(first_completion: str) -> None:
    signals = McpSignals(InMemorySignalFailureHandler())
    events: list[McpToolInvocationCompleted] = []
    signals.invocation_completed.connect("capture", events.append)
    publisher = McpInvocationPublisher(signals)
    lifecycle = publisher.start(McpToolIdentity("tool", None, None))
    evidence = InvocationReturnedFailure(InvocationFailureOrigin.INTERNAL)

    if first_completion == "success":
        publisher.succeeded(lifecycle)
    else:
        publisher.failed(lifecycle, McpToolInvocationFailureCategory.UNEXPECTED_ERROR, None, evidence)
    publisher.succeeded(lifecycle)
    publisher.failed(lifecycle, McpToolInvocationFailureCategory.UNEXPECTED_ERROR, None, evidence)

    assert len(events) == 1
    assert events[0].outcome.value == first_completion
