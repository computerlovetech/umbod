from typing import Any
from unittest.mock import Mock

import pytest
from fastmcp import Client

from umbod.core.agent_behaviour import AgentBehaviourService, DiagnosticReceipt, ReportQuery, StorageUnavailable, SubmitDiagnosticReport
from umbod.core.callers import CallerContext
from umbod.mcp.responses.recovery import recovery_instructions
from umbod.core.responses import OperationState

from .conftest import DiagnosticMcp, create_diagnostic_server
from .test_flow import submission


class FailingReportService(AgentBehaviourService):
    def __init__(self, delegate: AgentBehaviourService, after_commit: bool) -> None:
        self._delegate = delegate
        self._after_commit = after_commit

    async def submit_report(self, caller: CallerContext, command: SubmitDiagnosticReport) -> DiagnosticReceipt:
        if self._after_commit:
            await self._delegate.submit_report(caller, command)
        raise StorageUnavailable()


@pytest.mark.asyncio
@pytest.mark.parametrize("after_commit", [False, True])
async def test_possible_persistence_failure_requires_identical_key_and_payload_retry(diagnostic_mcp: DiagnosticMcp, after_commit: bool) -> None:
    server = create_diagnostic_server(FailingReportService(diagnostic_mcp.service, after_commit), diagnostic_mcp.callers, Mock())
    payload = submission()
    async with Client(server) as client:
        result = await client.call_tool("report_diagnostic", payload, raise_on_error=False)
    assert result.is_error
    assert result.structured_content is None
    guidance = result.meta["computerlove.tech/umbod"]["guidance"]
    assert guidance["error"]["code"] == "storage_unavailable"
    assert guidance["operation_state"] == "unknown"
    assert guidance["recovery"]["retry"] == "inspect_before_retry"
    text = " ".join(item.text for item in result.content)
    assert "identical payload" in text
    assert "same idempotency_key" in text
    assert "Never generate a replacement key" in text
    assert (await diagnostic_mcp.service.list_reports(ReportQuery())).total == int(after_commit)
    async with Client(diagnostic_mcp.server) as client:
        receipt = await client.call_tool("report_diagnostic", payload)
    assert receipt.structured_content["duplicate"] is after_commit


class UnrenderableReceipt(DiagnosticReceipt):
    def model_dump(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        raise ValueError("Unapproved renderer details")


class ReceiptRenderingFailureService(AgentBehaviourService):
    def __init__(self, delegate: AgentBehaviourService) -> None:
        self._delegate = delegate

    async def submit_report(self, caller: CallerContext, command: SubmitDiagnosticReport) -> DiagnosticReceipt:
        receipt = await self._delegate.submit_report(caller, command)
        return UnrenderableReceipt.model_validate(receipt.model_dump())


@pytest.mark.asyncio
async def test_receipt_render_failure_after_persistence_is_completed_not_silently_successful(diagnostic_mcp: DiagnosticMcp) -> None:
    server = create_diagnostic_server(ReceiptRenderingFailureService(diagnostic_mcp.service), diagnostic_mcp.callers, Mock())
    async with Client(server) as client:
        result = await client.call_tool("report_diagnostic", submission(), raise_on_error=False)
    assert result.is_error
    assert result.structured_content is None
    assert result.meta["computerlove.tech/umbod"]["guidance"]["operation_state"] == "completed"
    text = " ".join(item.text for item in result.content)
    assert "identical payload" in text
    assert "same idempotency_key" in text
    assert "Unapproved renderer details" not in text
    assert (await diagnostic_mcp.service.list_reports(ReportQuery())).total == 1


@pytest.mark.parametrize("state", [OperationState.UNKNOWN, OperationState.COMPLETED])
def test_response_render_failure_retains_model_visible_exact_retry_guidance(state: OperationState) -> None:
    arguments: dict[str, Any] = {}
    instructions = recovery_instructions("report_diagnostic", arguments, "tool_response_contract_invalid", state)
    assert "identical payload" in instructions[0]
    assert "same idempotency_key" in instructions[0]
    assert "never generate a replacement key" in instructions[0]
    assert "Do not claim success without a receipt" in instructions[1]
