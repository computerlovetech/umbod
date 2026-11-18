import asyncio
from dataclasses import replace
from unittest.mock import Mock

import pytest
from fastmcp.exceptions import AuthorizationError, ToolError, ValidationError
from pydantic import ValidationError as ModelValidationError

from umbod.core.capabilities import CapabilityIdentity
from umbod.core.usage.models import ConnectorUsageToolTarget
from umbod.core.invocation.diagnostics import InvocationFailureDiagnostic, NoInvocationFailureDiagnostic
from umbod.core.invocation.failure_evidence import (
    InvocationExceptionEvidence,
    InvocationFailureEvidence,
    InvocationFailureOrigin,
    InvocationRejectedFailure,
    InvocationReturnedFailure,
    capture_invocation_exception,
    capture_returned_failure,
    invocation_failure_scope,
)
from umbod.core.invocation.policy import ConnectorInvocation, ConnectorInvocationDenied
from umbod.core.invocation.tools.execution import ToolExecutionFailed, ToolExecutionInterceptor, ToolExecutionOutcome, ToolExecutionRequest, ToolExecutionSucceeded
from tests.support.signals import InMemorySignalFailureHandler
from umbod.mcp.signals import McpInvocationPublisher, McpInvocationPublishing, McpSignals, McpToolInvocationCompleted, McpToolInvocationFailed
from umbod.mcp.connectors.native.approval import ModernConnectorApprovalRequired
from umbod.mcp.signals import McpInvocationContext, reset_mcp_invocation_context, set_mcp_invocation_context
from umbod.mcp.signals.diagnostics import invocation_failure
from umbod.mcp.signals import McpInvocationActor, McpInvocationCorrelation, McpToolIdentity, McpToolInvocationFailureCategory, McpToolInvocationSucceeded
from umbod.mcp.signals import ConnectorInvocationSignalInterceptor
from umbod.mcp.tools.errors import ToolAuthorizationDenied
from umbod.mcp.signals.lifecycle import McpToolInvocationLifecycle, UnavailableToolInvocationLifecycle


class RecordingInvocationPublisher(McpInvocationPublishing):
    def __init__(self) -> None:
        self.started: list[McpToolIdentity] = []
        self.successes: list[McpToolInvocationLifecycle | UnavailableToolInvocationLifecycle] = []
        self.failures: list[tuple[McpToolInvocationLifecycle | UnavailableToolInvocationLifecycle, McpToolInvocationFailureCategory, InvocationFailureDiagnostic | NoInvocationFailureDiagnostic, InvocationFailureEvidence]] = []
        self.reported_errors: list[tuple[str, Exception]] = []

    def start(self, identity: McpToolIdentity) -> McpToolInvocationLifecycle | UnavailableToolInvocationLifecycle:
        self.started.append(identity)
        return McpToolInvocationLifecycle.start(identity)

    def succeeded(self, lifecycle: McpToolInvocationLifecycle | UnavailableToolInvocationLifecycle) -> None:
        self.successes.append(lifecycle)

    def failed(self, lifecycle: McpToolInvocationLifecycle | UnavailableToolInvocationLifecycle, category: McpToolInvocationFailureCategory, diagnostic: InvocationFailureDiagnostic | NoInvocationFailureDiagnostic, evidence: InvocationFailureEvidence) -> None:
        self.failures.append((lifecycle, category, diagnostic, evidence))

    def report_failure(self, name: str, error: Exception) -> None:
        self.reported_errors.append((name, error))


@pytest.fixture
def execution_request() -> ToolExecutionRequest:
    return ToolExecutionRequest(
        identity=CapabilityIdentity(connector_kind="openapi", connector_id="connector", capability_kind="tool", capability_key="operation"),
        public_tool_name="tool",
        arguments={},
    )


@pytest.mark.asyncio
async def test_injected_publisher_receives_successful_lifecycle(execution_request: ToolExecutionRequest) -> None:
    publisher = RecordingInvocationPublisher()

    def classify(result: object) -> bool:
        return False

    interceptor = ConnectorInvocationSignalInterceptor("name", publisher=publisher, result_is_error=classify)
    state = await interceptor.before_tool_preparation(execution_request)
    await interceptor.after_tool_execution(execution_request, ToolExecutionSucceeded(object()), state)

    assert len(publisher.started) == 1
    assert publisher.started[0].tool_name == execution_request.public_tool_name
    assert publisher.successes == [state]
    assert publisher.failures == []
    assert publisher.reported_errors == []


@pytest.mark.asyncio
async def test_injected_publisher_receives_classifier_error(execution_request: ToolExecutionRequest) -> None:
    publisher = RecordingInvocationPublisher()
    classifier_error = RuntimeError("private-classifier")

    def classify(result: object) -> bool:
        raise classifier_error

    interceptor = ConnectorInvocationSignalInterceptor("name", publisher=publisher, result_is_error=classify)
    state = await interceptor.before_tool_preparation(execution_request)
    await interceptor.after_tool_execution(execution_request, ToolExecutionSucceeded(object()), state)

    assert publisher.reported_errors == [("Connector tool result classification failed", classifier_error)]
    assert publisher.successes == []
    assert len(publisher.failures) == 1
    lifecycle, category, diagnostic, evidence = publisher.failures[0]
    assert lifecycle is state
    assert category == McpToolInvocationFailureCategory.CONNECTOR_ERROR
    assert isinstance(diagnostic, NoInvocationFailureDiagnostic)
    assert isinstance(evidence, InvocationExceptionEvidence)
    assert evidence.origin == InvocationFailureOrigin.INTERNAL
    assert evidence.exception_type == "RuntimeError"
    assert "private-classifier" not in repr(evidence)


@pytest.mark.asyncio
async def test_returned_openapi_failure_has_origin_without_exception(execution_request: ToolExecutionRequest) -> None:
    signals = McpSignals(InMemorySignalFailureHandler())
    events: list[McpToolInvocationCompleted] = []
    signals.invocation_completed.connect("capture", events.append)

    def classifier(result: object) -> bool:
        return True

    interceptor: ToolExecutionInterceptor = ConnectorInvocationSignalInterceptor("name", McpInvocationPublisher(signals), classifier)
    state = await interceptor.before_tool_preparation(execution_request)
    await interceptor.after_tool_execution(execution_request, ToolExecutionSucceeded(object()), state)
    assert len(events) == 1
    event = events[0]
    assert isinstance(event, McpToolInvocationFailed)
    assert event.failure_category == McpToolInvocationFailureCategory.TOOL_ERROR
    assert event.evidence == InvocationReturnedFailure(InvocationFailureOrigin.OPENAPI)
    assert isinstance(event.diagnostic, NoInvocationFailureDiagnostic)


@pytest.mark.asyncio
async def test_result_classifier_exception_becomes_internal_failure_without_raising(execution_request: ToolExecutionRequest) -> None:
    signals = McpSignals(InMemorySignalFailureHandler())
    events: list[McpToolInvocationCompleted] = []
    signals.invocation_completed.connect("capture", events.append)

    def classify(result: object) -> bool:
        raise RuntimeError("secret")

    interceptor: ToolExecutionInterceptor = ConnectorInvocationSignalInterceptor("name", McpInvocationPublisher(signals), classify)
    state = await interceptor.before_tool_preparation(execution_request)
    await interceptor.after_tool_execution(execution_request, ToolExecutionSucceeded(object()), state)
    assert len(events) == 1
    event = events[0]
    assert isinstance(event, McpToolInvocationFailed)
    assert event.failure_category == McpToolInvocationFailureCategory.CONNECTOR_ERROR
    assert isinstance(event.evidence, InvocationExceptionEvidence)
    assert event.evidence.origin == InvocationFailureOrigin.INTERNAL
    assert event.evidence.exception_type == "RuntimeError"
    assert "secret" not in repr(event)


@pytest.mark.asyncio
async def test_classifier_exception_remains_internal_despite_rejection_diagnostic(execution_request: ToolExecutionRequest) -> None:
    failure_handler = InMemorySignalFailureHandler()
    signals = McpSignals(failure_handler)
    events: list[McpToolInvocationCompleted] = []
    signals.invocation_completed.connect("capture", events.append)

    def classify(result: object) -> bool:
        raise RuntimeError("private-classifier")

    interceptor = ConnectorInvocationSignalInterceptor("name", McpInvocationPublisher(signals), classify)
    diagnostic = InvocationFailureDiagnostic(execution_mode="personal", stage="arguments", reason="invalid_arguments")
    token = invocation_failure.set(diagnostic)
    try:
        with invocation_failure_scope():
            capture_returned_failure(InvocationFailureOrigin.MCP)
            state = await interceptor.before_tool_preparation(execution_request)
            await interceptor.after_tool_execution(execution_request, ToolExecutionSucceeded(object()), state)
    finally:
        invocation_failure.reset(token)

    assert len(events) == 1
    event = events[0]
    assert isinstance(event, McpToolInvocationFailed)
    assert event.failure_category == McpToolInvocationFailureCategory.CONNECTOR_ERROR
    assert event.diagnostic is diagnostic
    assert isinstance(event.evidence, InvocationExceptionEvidence)
    assert event.evidence.origin == InvocationFailureOrigin.INTERNAL
    assert "private-classifier" not in repr(event)


@pytest.mark.asyncio
async def test_cancellation_does_not_publish_completion(execution_request: ToolExecutionRequest) -> None:
    signals = McpSignals(InMemorySignalFailureHandler())
    events: list[McpToolInvocationCompleted] = []
    signals.invocation_completed.connect("capture", events.append)

    def classifier(result: object) -> bool:
        return False

    interceptor: ToolExecutionInterceptor = ConnectorInvocationSignalInterceptor("name", McpInvocationPublisher(signals), classifier)
    state = await interceptor.before_tool_preparation(execution_request)
    await interceptor.after_tool_execution(execution_request, ToolExecutionFailed(asyncio.CancelledError()), state)
    assert events == []


@pytest.mark.asyncio
@pytest.mark.parametrize("outcome", [ToolExecutionSucceeded(object()), ToolExecutionFailed(RuntimeError("failed"))])
async def test_unavailable_lifecycle_does_not_publish_completion(
    execution_request: ToolExecutionRequest, outcome: ToolExecutionOutcome,
) -> None:
    signals = McpSignals(InMemorySignalFailureHandler())
    events: list[McpToolInvocationCompleted] = []
    signals.invocation_completed.connect("capture", events.append)
    classifier = Mock(return_value=False)
    interceptor = ConnectorInvocationSignalInterceptor("name", McpInvocationPublisher(signals), classifier)

    await interceptor.after_tool_execution(execution_request, outcome, UnavailableToolInvocationLifecycle())

    assert events == []
    classifier.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("state", [None, object(), "invalid"])
async def test_invalid_lifecycle_state_is_rejected(execution_request: ToolExecutionRequest, state: object) -> None:
    interceptor = ConnectorInvocationSignalInterceptor("name", McpInvocationPublisher(McpSignals(InMemorySignalFailureHandler())), Mock())

    with pytest.raises(TypeError, match="Invalid connector invocation lifecycle state"):
        await interceptor.after_tool_execution(execution_request, ToolExecutionSucceeded(object()), state)


@pytest.mark.asyncio
async def test_start_failure_returns_unavailable_connector_state(
    execution_request: ToolExecutionRequest, monkeypatch: pytest.MonkeyPatch,
) -> None:
    signals = McpSignals(InMemorySignalFailureHandler())
    events: list[McpToolInvocationCompleted] = []
    signals.invocation_completed.connect("capture", events.append)
    monkeypatch.setattr(McpToolInvocationLifecycle, "start", Mock(side_effect=RuntimeError("private-start-token")))
    interceptor = ConnectorInvocationSignalInterceptor("name", McpInvocationPublisher(signals), Mock(return_value=False))

    state = await interceptor.before_tool_preparation(execution_request)
    await interceptor.after_tool_execution(execution_request, ToolExecutionSucceeded(object()), state)

    assert isinstance(state, UnavailableToolInvocationLifecycle)
    assert events == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("error", "category"),
    [
        (ValidationError("private-input"), McpToolInvocationFailureCategory.VALIDATION),
        (ConnectorInvocationDenied("private-input"), McpToolInvocationFailureCategory.AUTHORIZATION),
        (AuthorizationError("private-input"), McpToolInvocationFailureCategory.AUTHORIZATION),
        (ToolAuthorizationDenied("private-input"), McpToolInvocationFailureCategory.AUTHORIZATION),
    ],
)
async def test_explicit_rejection_has_client_evidence_without_stacktrace(
    execution_request: ToolExecutionRequest, error: Exception, category: McpToolInvocationFailureCategory,
) -> None:
    signals = McpSignals(InMemorySignalFailureHandler())
    events: list[McpToolInvocationCompleted] = []
    signals.invocation_completed.connect("capture", events.append)
    classifier = Mock(return_value=False)
    interceptor = ConnectorInvocationSignalInterceptor("name", McpInvocationPublisher(signals), classifier)

    with invocation_failure_scope():
        state = await interceptor.before_tool_preparation(execution_request)
        await interceptor.after_tool_execution(execution_request, ToolExecutionFailed(error), state)

    assert len(events) == 1
    event = events[0]
    assert isinstance(event, McpToolInvocationFailed)
    assert event.failure_category == category
    assert event.evidence == InvocationRejectedFailure(InvocationFailureOrigin.CLIENT_INPUT)
    assert "private-input" not in repr(event)
    classifier.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error",
    [
        ValueError("private-error"),
        RuntimeError("private-error"),
        ToolError("private-error"),
        ModelValidationError.from_exception_data("private-error", []),
    ],
)
async def test_non_rejection_exception_remains_server_fault(
    execution_request: ToolExecutionRequest, error: Exception,
) -> None:
    signals = McpSignals(InMemorySignalFailureHandler())
    events: list[McpToolInvocationCompleted] = []
    signals.invocation_completed.connect("capture", events.append)
    interceptor = ConnectorInvocationSignalInterceptor("name", McpInvocationPublisher(signals), Mock(return_value=False))

    with invocation_failure_scope():
        state = await interceptor.before_tool_preparation(execution_request)
        await interceptor.after_tool_execution(execution_request, ToolExecutionFailed(error), state)

    assert len(events) == 1
    event = events[0]
    assert isinstance(event, McpToolInvocationFailed)
    assert event.failure_category == McpToolInvocationFailureCategory.CONNECTOR_ERROR
    assert isinstance(event.evidence, InvocationExceptionEvidence)
    assert event.evidence.exception_type == type(error).__qualname__
    assert "private-error" not in repr(event)


@pytest.mark.asyncio
@pytest.mark.parametrize("returned_error", [True, False])
async def test_preserved_exception_evidence_remains_server_fault_with_correlation_and_privacy(
    execution_request: ToolExecutionRequest, returned_error: bool,
) -> None:
    signals = McpSignals(InMemorySignalFailureHandler())
    events: list[McpToolInvocationCompleted] = []
    signals.invocation_completed.connect("capture", events.append)
    interceptor = ConnectorInvocationSignalInterceptor("name", McpInvocationPublisher(signals), Mock(return_value=returned_error))
    correlation = McpInvocationCorrelation(trace_id="trace", span_id="span")
    actor = McpInvocationActor(authenticated_user_id="user")
    token = set_mcp_invocation_context(McpInvocationContext(actor=actor, correlation=correlation, server_name="server"))
    try:
        with invocation_failure_scope():
            try:
                raise RuntimeError("private-credential")
            except RuntimeError as error:
                evidence = capture_invocation_exception(error, InvocationFailureOrigin.MCP)
            state = await interceptor.before_tool_preparation(execution_request)
            outcome = ToolExecutionSucceeded({"private-result": "private-credential"}) if returned_error else ToolExecutionFailed(ConnectorInvocationDenied("private-credential"))
            await interceptor.after_tool_execution(execution_request, outcome, state)
    finally:
        reset_mcp_invocation_context(token)

    assert len(events) == 1
    event = events[0]
    assert isinstance(event, McpToolInvocationFailed)
    assert event.failure_category == McpToolInvocationFailureCategory.CONNECTOR_ERROR
    assert event.evidence is evidence
    assert "test_preserved_exception_evidence" in evidence.stacktrace
    assert event.started.correlation == correlation
    assert event.started.actor == actor
    assert "private-credential" not in repr(event)
    assert "private-result" not in repr(event)


@pytest.mark.asyncio
async def test_backend_diagnostic_maps_returned_failure_to_connector_error(execution_request: ToolExecutionRequest) -> None:
    signals = McpSignals(InMemorySignalFailureHandler())
    events: list[McpToolInvocationCompleted] = []
    signals.invocation_completed.connect("capture", events.append)
    interceptor = ConnectorInvocationSignalInterceptor("name", McpInvocationPublisher(signals), Mock(return_value=True))
    diagnostic = InvocationFailureDiagnostic(execution_mode="personal", stage="runtime", reason="runtime_failure")
    response = {"error": "unchanged"}
    outcome = ToolExecutionSucceeded(response)
    token = invocation_failure.set(diagnostic)
    try:
        with invocation_failure_scope():
            state = await interceptor.before_tool_preparation(execution_request)
            await interceptor.after_tool_execution(execution_request, outcome, state)
    finally:
        invocation_failure.reset(token)

    assert len(events) == 1
    event = events[0]
    assert isinstance(event, McpToolInvocationFailed)
    assert event.failure_category == McpToolInvocationFailureCategory.CONNECTOR_ERROR
    assert event.diagnostic is diagnostic
    assert event.evidence == InvocationReturnedFailure(InvocationFailureOrigin.OPENAPI)
    assert outcome.result is response
    assert response == {"error": "unchanged"}


@pytest.mark.asyncio
@pytest.mark.parametrize("connector_kind", ["native", "downstream_mcp", "openapi"])
async def test_returned_failure_preserves_recorded_origin(
    execution_request: ToolExecutionRequest, connector_kind: str,
) -> None:
    signals = McpSignals(InMemorySignalFailureHandler())
    events: list[McpToolInvocationCompleted] = []
    signals.invocation_completed.connect("capture", events.append)
    interceptor = ConnectorInvocationSignalInterceptor("name", McpInvocationPublisher(signals), Mock(return_value=True))
    request = replace(execution_request, identity=execution_request.identity.model_copy(update={"connector_kind": connector_kind}))

    with invocation_failure_scope():
        evidence = capture_returned_failure(InvocationFailureOrigin.CONNECTOR)
        state = await interceptor.before_tool_preparation(request)
        await interceptor.after_tool_execution(request, ToolExecutionSucceeded(object()), state)

    assert len(events) == 1
    event = events[0]
    assert isinstance(event, McpToolInvocationFailed)
    assert event.failure_category == McpToolInvocationFailureCategory.TOOL_ERROR
    assert event.evidence is evidence


@pytest.mark.asyncio
async def test_successful_result_publishes_success_without_changing_response(execution_request: ToolExecutionRequest) -> None:
    signals = McpSignals(InMemorySignalFailureHandler())
    events: list[McpToolInvocationCompleted] = []
    signals.invocation_completed.connect("capture", events.append)
    response = {"content": [{"text": "unchanged"}]}
    outcome = ToolExecutionSucceeded(response)
    classifier = Mock(return_value=False)
    interceptor = ConnectorInvocationSignalInterceptor("name", McpInvocationPublisher(signals), classifier)
    state = await interceptor.before_tool_preparation(execution_request)

    await interceptor.after_tool_execution(execution_request, outcome, state)

    assert len(events) == 1
    assert isinstance(events[0], McpToolInvocationSucceeded)
    assert events[0].started.tool.usage_target == ConnectorUsageToolTarget(
        kind='connector', connector_kind='openapi', connector_id='connector', capability_key='operation',
    )
    assert outcome.result is response
    assert response == {"content": [{"text": "unchanged"}]}
    classifier.assert_called_once_with(response)


@pytest.mark.asyncio
async def test_success_is_not_overridden_by_existing_failure_context(execution_request: ToolExecutionRequest) -> None:
    signals = McpSignals(InMemorySignalFailureHandler())
    events: list[McpToolInvocationCompleted] = []
    signals.invocation_completed.connect("capture", events.append)
    response = {"content": [{"text": "unchanged"}]}
    classifier = Mock(return_value=False)
    interceptor = ConnectorInvocationSignalInterceptor("name", McpInvocationPublisher(signals), classifier)
    token = invocation_failure.set(InvocationFailureDiagnostic(execution_mode="personal", stage="runtime", reason="runtime_failure"))
    try:
        with invocation_failure_scope():
            capture_invocation_exception(RuntimeError("private-prior-failure"), InvocationFailureOrigin.MCP)
            state = await interceptor.before_tool_preparation(execution_request)
            await interceptor.after_tool_execution(execution_request, ToolExecutionSucceeded(response), state)
    finally:
        invocation_failure.reset(token)

    assert len(events) == 1
    assert isinstance(events[0], McpToolInvocationSucceeded)
    assert "private-prior-failure" not in repr(events[0])
    classifier.assert_called_once_with(response)


@pytest.mark.asyncio
async def test_rejection_diagnostic_overrides_captured_exception_in_published_event(execution_request: ToolExecutionRequest) -> None:
    signals = McpSignals(InMemorySignalFailureHandler())
    events: list[McpToolInvocationCompleted] = []
    signals.invocation_completed.connect("capture", events.append)
    interceptor = ConnectorInvocationSignalInterceptor("name", McpInvocationPublisher(signals), Mock(return_value=False))
    diagnostic = InvocationFailureDiagnostic(execution_mode="personal", stage="arguments", reason="invalid_arguments")
    token = invocation_failure.set(diagnostic)
    try:
        with invocation_failure_scope():
            capture_invocation_exception(RuntimeError("private-rejection"), InvocationFailureOrigin.INTERNAL)
            state = await interceptor.before_tool_preparation(execution_request)
            await interceptor.after_tool_execution(execution_request, ToolExecutionFailed(RuntimeError("private-wrapper")), state)
    finally:
        invocation_failure.reset(token)

    assert len(events) == 1
    event = events[0]
    assert isinstance(event, McpToolInvocationFailed)
    assert event.failure_category == McpToolInvocationFailureCategory.VALIDATION
    assert event.diagnostic is diagnostic
    assert event.evidence == InvocationRejectedFailure(InvocationFailureOrigin.CLIENT_INPUT)
    assert "private-rejection" not in repr(event)
    assert "private-wrapper" not in repr(event)


@pytest.mark.asyncio
async def test_modern_approval_required_does_not_publish_completion(execution_request: ToolExecutionRequest) -> None:
    signals = McpSignals(InMemorySignalFailureHandler())
    events: list[McpToolInvocationCompleted] = []
    signals.invocation_completed.connect("capture", events.append)
    classifier = Mock(return_value=False)
    interceptor = ConnectorInvocationSignalInterceptor("name", McpInvocationPublisher(signals), classifier)
    state = await interceptor.before_tool_preparation(execution_request)
    invocation = ConnectorInvocation.create(
        connector_kind="openapi", connector_id="connector", operation_name="operation", public_tool_name="tool", arguments={},
    )
    error = ModernConnectorApprovalRequired(invocation, 1, Mock())

    await interceptor.after_tool_execution(execution_request, ToolExecutionFailed(error), state)

    assert events == []
    classifier.assert_not_called()
