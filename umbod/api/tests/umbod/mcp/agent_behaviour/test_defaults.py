import json
from uuid import uuid4

import pytest
from fastmcp import Client

from umbod.core.agent_behaviour import PublishConfiguration, ReportQuery

from .conftest import DiagnosticMcp


@pytest.mark.asyncio
async def test_initial_direct_mcp_discovery_and_instructions_use_defaults(default_diagnostic_mcp: DiagnosticMcp) -> None:
    async with Client(default_diagnostic_mcp.server) as client:
        assert [tool.name for tool in await client.list_tools()] == ["report_diagnostic"]
        index = json.loads((await client.read_resource("umbod://agent-behaviour/playbooks"))[0].text)
        assert index == {"configuration_revision": 1, "playbooks": [{"id": "behaviour-review", "name": "Behaviour review", "allow_proactive": False, "resource_uri": "umbod://agent-behaviour/playbooks/behaviour-review"}]}
        instructions = json.loads((await client.read_resource("umbod://agent-behaviour/playbooks/behaviour-review"))[0].text)
        assert instructions["configuration_revision"] == 1
        assert {pattern["id"] for pattern in instructions["patterns"]} == {"missing-context", "tool-problems", "task-blocked", "user-correction"}
        assert all(pattern["enabled"] for pattern in instructions["patterns"])
        prompt = await client.get_prompt("run_diagnostics", {"playbook_id": "behaviour-review"})
        assert index["playbooks"][0]["resource_uri"] in prompt.messages[0].content.text
    assert (await default_diagnostic_mcp.service.list_reports(ReportQuery())).total == 0


@pytest.mark.asyncio
async def test_mcp_discovery_omits_dormant_settings_and_resolves_only_enabled_patterns(default_diagnostic_mcp: DiagnosticMcp) -> None:
    service = default_diagnostic_mcp.service
    defaults = await service.get_configuration()
    patterns = tuple(pattern.model_copy(update={"enabled": False}) if pattern.id == "missing-context" else pattern for pattern in defaults.patterns)
    await service.publish_configuration(PublishConfiguration(expected_revision=1, patterns=patterns, playbooks=defaults.playbooks))
    async with Client(default_diagnostic_mcp.server) as client:
        instructions = json.loads((await client.read_resource("umbod://agent-behaviour/playbooks/behaviour-review"))[0].text)
        assert instructions["playbook"]["pattern_ids"] == ["tool-problems", "task-blocked", "user-correction"]
        assert len(instructions["patterns"]) == 3
        await service.publish_configuration(PublishConfiguration(expected_revision=2, patterns=(), playbooks=defaults.playbooks))
        index = json.loads((await client.read_resource("umbod://agent-behaviour/playbooks"))[0].text)
        assert index["playbooks"] == []
        assert (await service.get_configuration()).playbooks == defaults.playbooks


@pytest.mark.asyncio
async def test_default_mcp_proactive_report_is_rejected_before_persistence(default_diagnostic_mcp: DiagnosticMcp) -> None:
    async with Client(default_diagnostic_mcp.server) as client:
        result = await client.call_tool("report_diagnostic", {
            "idempotency_key": str(uuid4()), "configuration_revision": 1, "playbook_id": "behaviour-review", "trigger": "proactive",
            "assessments": [{"pattern_id": pattern.id, "status": "not_assessed", "summary": "Context unavailable", "evidence": []} for pattern in default_diagnostic_mcp.service.get_defaults().patterns],
        }, raise_on_error=False)
    assert result.is_error is True
    guidance = result.meta["computerlove.tech/umbod"]["guidance"]
    assert guidance["error"]["code"] == "proactive_disabled"
    assert guidance["operation_state"] == "not_started"
    assert (await default_diagnostic_mcp.service.list_reports(ReportQuery())).total == 0
