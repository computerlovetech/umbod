import pytest

from tests.umbod.core.downstream_mcp_connectors.test_personal_runtime_authorizations import RuntimeCase, runtime_case
from umbod.core.connectors.downstream_mcp.personal_connections.health_models import PersonalAuthorizationHealthUnavailable, RejectPersonalAuthorization
from umbod.core.connectors.downstream_mcp.personal_connections.runtime_models import PersonalAuthorizationRejected, PersonalRuntimeUnavailable, PersonalToolCall, PersonalToolResult

from .runtime_support import execution_case, runtime_for_caller
from umbod.core.connectors.downstream_mcp.personal_connections import UnavailablePersonalCaller

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
        raise PersonalAuthorizationRejected("Personal MCP unavailable")

    async def unavailable(command: RejectPersonalAuthorization) -> None:
        raise PersonalAuthorizationHealthUnavailable("Personal authorization health unavailable")

    monkeypatch.setattr(execution.transport, "call_tool", rejected)
    monkeypatch.setattr(runtime_case.bundle.personal_tool_access, "reject_authorization", unavailable)
    with pytest.raises(PersonalAuthorizationHealthUnavailable):
        await execution.runtime.execute(execution.command)
