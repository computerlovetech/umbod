import pytest

from tests.umbod.core.downstream_mcp_connectors.test_personal_runtime_authorizations import RuntimeCase, runtime_case
from umbod.core.connectors.downstream_mcp.personal_connections.health_models import PersonalAuthorizationHealthUnavailable, RejectPersonalAuthorization
from umbod.core.connectors.downstream_mcp.personal_connections.runtime_models import PersonalAuthorizationRejected, PersonalRuntimeUnavailable, PersonalToolCall, PersonalToolResult

from .runtime_support import execution_case, runtime_for_caller
from umbod.core.connectors.downstream_mcp.personal_connections import UnavailablePersonalCaller
from umbod.core.invocation.failure_evidence import (
    InvocationExceptionEvidence,
    InvocationFailureOrigin,
    capture_invocation_exception,
    current_invocation_failure,
    invocation_failure_scope,
)

__all__ = ["runtime_case"]


@pytest.mark.asyncio
@pytest.mark.parametrize("reason", ["context_unavailable", "admission_denied", "invalid_arguments", "invalid_output", "downstream_tool_error"])
async def test_runtime_preserves_safe_diagnostics_before_redaction(runtime_case: RuntimeCase, reason: str) -> None:
    execution = await execution_case(runtime_case)
    command = execution.command
    runtime = execution.runtime
    if reason == "context_unavailable":
        runtime = runtime_for_caller(execution, UnavailablePersonalCaller(kind="unavailable"))
    elif reason == "admission_denied":
        await runtime_case.bundle.personal_connections.disconnect(runtime_case.query.key)
    elif reason == "invalid_arguments":
        command = command.model_copy(update={"arguments": {"value": 123}})
    elif reason == "downstream_tool_error":
        execution.transport.results[(runtime_case.query.key, "read")] = PersonalToolResult(result={"content": [{"type": "text", "text": "sensitive-sentinel"}], "isError": True})
    else:
        execution.transport.results[(runtime_case.query.key, "read")] = PersonalToolResult(result={"content": [], "structuredContent": "sensitive-sentinel"})
    with pytest.raises(PersonalRuntimeUnavailable) as caught:
        await runtime.execute(command)
    assert caught.value.diagnostic.reason == reason
    assert str(caught.value) == "Personal tool unavailable"
    assert caught.value.__context__ is None
    assert "sensitive-sentinel" not in repr(caught.value.diagnostic)


@pytest.mark.asyncio
async def test_rejection_health_persistence_failure_keeps_its_distinct_exception(runtime_case: RuntimeCase, monkeypatch: pytest.MonkeyPatch) -> None:
    execution = await execution_case(runtime_case)

    async def rejected(command: PersonalToolCall) -> PersonalToolResult:
        try:
            raise PersonalAuthorizationRejected("sensitive-rejected-token")
        except PersonalAuthorizationRejected as error:
            capture_invocation_exception(error, InvocationFailureOrigin.MCP)
            raise

    async def unavailable(command: RejectPersonalAuthorization) -> None:
        evidence = current_invocation_failure()
        assert isinstance(evidence, InvocationExceptionEvidence)
        assert evidence.origin == InvocationFailureOrigin.MCP
        assert evidence.exception_type == "PersonalAuthorizationRejected"
        raise PersonalAuthorizationHealthUnavailable("sensitive-persistence-token")

    monkeypatch.setattr(execution.transport, "call_tool", rejected)
    monkeypatch.setattr(runtime_case.bundle.personal_tool_access, "reject_authorization", unavailable)
    with invocation_failure_scope():
        with pytest.raises(PersonalAuthorizationHealthUnavailable, match="sensitive-persistence-token"):
            await execution.runtime.execute(execution.command)
        evidence = current_invocation_failure()
        assert isinstance(evidence, InvocationExceptionEvidence)
        assert evidence.origin == InvocationFailureOrigin.INTERNAL
        assert evidence.exception_type == "PersonalAuthorizationHealthUnavailable"
        assert "in unavailable" in evidence.stacktrace
        assert "sensitive-rejected-token" not in evidence.stacktrace
        assert "sensitive-persistence-token" not in evidence.stacktrace


@pytest.mark.asyncio
@pytest.mark.parametrize("lower_boundary", [False, True])
async def test_runtime_preserves_original_safe_exception_evidence(runtime_case: RuntimeCase, monkeypatch: pytest.MonkeyPatch, lower_boundary: bool) -> None:
    execution = await execution_case(runtime_case)

    async def fail(command: PersonalToolCall) -> PersonalToolResult:
        try:
            raise ValueError("sensitive-original-token")
        except ValueError as error:
            if lower_boundary:
                capture_invocation_exception(error, InvocationFailureOrigin.MCP)
                raise PersonalRuntimeUnavailable("Personal MCP unavailable") from None
            raise RuntimeError("sensitive-wrapper-token") from error

    monkeypatch.setattr(execution.transport, "call_tool", fail)
    with invocation_failure_scope():
        with pytest.raises(PersonalRuntimeUnavailable):
            await execution.runtime.execute(execution.command)
        evidence = current_invocation_failure()
        assert isinstance(evidence, InvocationExceptionEvidence)
        assert evidence.origin == (InvocationFailureOrigin.MCP if lower_boundary else InvocationFailureOrigin.INTERNAL)
        assert evidence.exception_type == ("ValueError" if lower_boundary else "RuntimeError")
        assert "in fail" in evidence.stacktrace
        assert "ValueError" in evidence.stacktrace
        assert "sensitive-original-token" not in evidence.stacktrace
        assert "sensitive-wrapper-token" not in evidence.stacktrace
