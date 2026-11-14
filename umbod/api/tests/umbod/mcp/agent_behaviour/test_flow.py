import json
from uuid import uuid4

import pytest
from fastmcp import Client

from umbod.core.agent_behaviour import ReportQuery

from .conftest import DiagnosticMcp


def submission() -> dict[str, object]:
    return {"idempotency_key": str(uuid4()), "configuration_revision": 2, "playbook_id": "review", "trigger": "user_requested", "assessments": [{"pattern_id": "fallback", "status": "observed", "summary": "Context was unavailable", "evidence": ["Requested context was absent"]}]}


@pytest.mark.asyncio
async def test_prompt_embeds_current_bundle_and_privacy_without_writing(diagnostic_mcp: DiagnosticMcp) -> None:
    async with Client(diagnostic_mcp.server) as client:
        prompt = await client.get_prompt("run_diagnostics", {"playbook_id": "review"})
        text = prompt.messages[0].content.text
        assert prompt.messages[0].role == "user"
        for required in ["Review available authorized facts", "Assess fallback", "Normal clarification", '"configuration_revision":2', "report_diagnostic", "hidden reasoning", "same UUID", "not_assessed", "Slash-command"]:
            assert required in text
    assert (await diagnostic_mcp.service.list_reports(ReportQuery())).total == 0


@pytest.mark.asyncio
async def test_report_returns_durable_receipt_and_exact_retry_without_observing_prose(diagnostic_mcp: DiagnosticMcp) -> None:
    payload = submission()
    async with Client(diagnostic_mcp.server) as client:
        first = await client.call_tool("report_diagnostic", payload)
        duplicate = await client.call_tool("report_diagnostic", payload)
    assert first.structured_content["duplicate"] is False
    assert duplicate.structured_content == {**first.structured_content, "duplicate": True}
    assert first.meta["computerlove.tech/umbod"]["guidance"]["operation_state"] == "completed"
    assert (await diagnostic_mcp.service.list_reports(ReportQuery())).total == 1
    assert "Requested context was absent" not in str(diagnostic_mcp.observations.mock_calls)
    assert "Context was unavailable" not in str(diagnostic_mcp.observations.mock_calls)
    assert json.loads(first.content[0].text) == first.structured_content


@pytest.mark.asyncio
@pytest.mark.parametrize("change,code", [({"trigger": "proactive"}, "proactive_disabled"), ({"configuration_revision": 3}, "stale_configuration"), ({"transcript": "forbidden"}, "report_invalid")])
async def test_rejected_report_is_not_started_and_creates_no_report(diagnostic_mcp: DiagnosticMcp, change: dict[str, object], code: str) -> None:
    async with Client(diagnostic_mcp.server) as client:
        result = await client.call_tool("report_diagnostic", {**submission(), **change}, raise_on_error=False)
    assert result.is_error
    guidance = result.meta["computerlove.tech/umbod"]["guidance"]
    assert guidance["operation_state"] == "not_started"
    assert guidance["error"]["code"] == code
    assert (await diagnostic_mcp.service.list_reports(ReportQuery())).total == 0
