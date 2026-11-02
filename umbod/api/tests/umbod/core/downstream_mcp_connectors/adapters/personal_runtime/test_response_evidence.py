from datetime import datetime, timezone

import anyio
import pytest
from pydantic import ValidationError

from umbod.core.connectors.downstream_mcp.adapters.personal_runtime.http import ResponseHeaderObserver
from umbod.core.connectors.downstream_mcp.adapters.personal_runtime.operation import OperationState
from umbod.core.connectors.downstream_mcp.personal_connections.runtime_models import PersonalRuntimeLimits, PersonalRuntimeTarget, PersonalRuntimeUnavailable
from umbod.core.invocation.diagnostics import DownstreamHttpResponse, InvocationFailureDiagnostic, NoDownstreamResponse
from umbod.core.invocation.failure_evidence import InvocationExceptionEvidence, current_invocation_failure, invocation_failure_scope

from .conftest import ScriptedNetwork, ScriptedResolver, make_transport


def test_diagnostic_defaults_to_explicit_no_response_for_existing_constructors() -> None:
    diagnostic = InvocationFailureDiagnostic(execution_mode="personal", stage="transport", reason="timeout")
    assert diagnostic.downstream_response == NoDownstreamResponse()
    assert diagnostic.model_dump()["downstream_response"] == {"kind": "no_response"}


@pytest.mark.parametrize("status", [99, 600])
def test_http_evidence_rejects_invalid_status(status: int) -> None:
    with pytest.raises(ValidationError):
        DownstreamHttpResponse(status_code=status)


def test_diagnostic_reason_is_allowlisted_and_response_evidence_is_immutable() -> None:
    with pytest.raises(ValidationError):
        InvocationFailureDiagnostic(execution_mode="personal", stage="transport", reason="untrusted-provider-message")
    response = DownstreamHttpResponse(status_code=503)
    with pytest.raises(ValidationError):
        response.status_code = 200
    with pytest.raises(ValidationError):
        InvocationFailureDiagnostic(execution_mode="personal", stage="transport", reason="timeout", downstream_response={"kind": "no_response", "status_code": 503})


@pytest.mark.asyncio
async def test_first_failure_keeps_reason_status_and_evidence_through_secondary_cleanup(target: PersonalRuntimeTarget, limits: PersonalRuntimeLimits) -> None:
    with invocation_failure_scope(), anyio.CancelScope() as scope:
        state = OperationState(target, limits, lambda: datetime.now(timezone.utc), scope, target)
        state.response_evidence = DownstreamHttpResponse(status_code=429)
        with pytest.raises(PersonalRuntimeUnavailable):
            state.reject("http_rejected")
        first_evidence = current_invocation_failure()
        assert isinstance(first_evidence, InvocationExceptionEvidence)
        assert first_evidence.origin.value == "downstream_mcp"
        state.response_evidence = DownstreamHttpResponse(status_code=500)
        state.cleaning_up = True
        with pytest.raises(PersonalRuntimeUnavailable) as caught:
            state.reject("network_failure")
        assert caught.value.diagnostic.reason == "http_rejected"
        assert caught.value.diagnostic.downstream_response == DownstreamHttpResponse(status_code=429)
        assert current_invocation_failure() is first_evidence
        assert scope.cancel_called


@pytest.mark.asyncio
async def test_informational_headers_do_not_reject_valid_final_response(target: PersonalRuntimeTarget, limits: PersonalRuntimeLimits, network: ScriptedNetwork) -> None:
    network.interim_response = True
    network.read_size = 3
    inventory = await make_transport(limits, network, ScriptedResolver()).list_tools(target)
    assert tuple(tool.identity.downstream_name for tool in inventory.tools) == ("lookup",)


@pytest.mark.asyncio
@pytest.mark.parametrize("length", [b"-1", b"invalid", b"1, 2", b""])
async def test_fragmented_malformed_content_length_preserves_numeric_status(target: PersonalRuntimeTarget, limits: PersonalRuntimeLimits, length: bytes) -> None:
    with invocation_failure_scope(), anyio.CancelScope() as scope:
        state = OperationState(target, limits, lambda: datetime.now(timezone.utc), scope, target)
        observe = ResponseHeaderObserver(state)
        observe(b"HTTP/1.1 200 OK\r\nContent-Len")
        with pytest.raises(PersonalRuntimeUnavailable) as caught:
            observe(b"gth: " + length + b"\r\n\r\n")
        assert caught.value.diagnostic.reason == "invalid_content_length"
        assert caught.value.diagnostic.downstream_response == DownstreamHttpResponse(status_code=200)
