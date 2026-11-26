import json
from uuid import uuid4

import pytest
from fastmcp import Client

from umbod.core.agent_behaviour import PublishConfiguration, ReportQuery

from .conftest import DiagnosticMcp

INDEX = "umbod://agent-behaviour/playbooks"
INSTRUCTIONS = f"{INDEX}/behaviour-review"


@pytest.mark.asyncio
async def test_default_reporting_can_be_enabled_and_disabled_in_the_same_mcp_session(default_diagnostic_mcp: DiagnosticMcp) -> None:
    service = default_diagnostic_mcp.service

    @default_diagnostic_mcp.server.tool
    def unrelated_tool() -> str:
        return "available"

    async with Client(default_diagnostic_mcp.server) as client:
        assert [tool.name for tool in await client.list_tools()] == ["unrelated_tool"]
        assert await client.list_prompts() == []
        assert await client.list_resources() == []
        assert await client.list_resource_templates() == []

        defaults = await service.get_configuration()
        enabled = await service.publish_configuration(PublishConfiguration(
            expected_revision=defaults.revision, reporting_enabled=True, patterns=defaults.patterns, playbooks=defaults.playbooks,
        ))
        assert {tool.name for tool in await client.list_tools()} == {"unrelated_tool", "report_diagnostic"}
        assert [prompt.name for prompt in await client.list_prompts()] == ["run_diagnostics"]
        assert [str(resource.uri) for resource in await client.list_resources()] == [INDEX]
        assert [template.uri_template for template in await client.list_resource_templates()] == [f"{INDEX}/{{playbook_id}}"]
        index = json.loads((await client.read_resource(INDEX))[0].text)
        assert index == {"configuration_revision": enabled.revision, "playbooks": [{"id": "behaviour-review", "name": "Behaviour review", "resource_uri": INSTRUCTIONS}]}
        instructions = json.loads((await client.read_resource(INSTRUCTIONS))[0].text)
        assert instructions["configuration_revision"] == enabled.revision
        assert {pattern["id"] for pattern in instructions["patterns"]} == {"missing-context", "tool-problems", "task-blocked", "user-correction"}
        prompt = await client.get_prompt("run_diagnostics", {"playbook_id": "behaviour-review"})
        assert INSTRUCTIONS in prompt.messages[0].content.text

        arguments = {
            "idempotency_key": str(uuid4()), "configuration_revision": enabled.revision, "playbook_id": "behaviour-review", "trigger": "proactive",
            "assessments": [{"pattern_id": pattern.id, "status": "not_assessed", "summary": "Context unavailable", "evidence": []} for pattern in defaults.patterns],
        }
        receipt = await client.call_tool("report_diagnostic", arguments)
        await service.publish_configuration(PublishConfiguration(
            expected_revision=enabled.revision, reporting_enabled=False, patterns=defaults.patterns, playbooks=defaults.playbooks,
        ))
        assert [tool.name for tool in await client.list_tools()] == ["unrelated_tool"]
        assert await client.list_prompts() == []
        assert await client.list_resources() == []
        assert await client.list_resource_templates() == []
        for uri in (INDEX, INSTRUCTIONS):
            with pytest.raises(Exception, match="reporting_disabled"):
                await client.read_resource(uri)
        with pytest.raises(Exception, match="reporting_disabled"):
            await client.get_prompt("run_diagnostics", {"playbook_id": "behaviour-review"})
        for key in (arguments["idempotency_key"], str(uuid4())):
            result = await client.call_tool("report_diagnostic", {**arguments, "idempotency_key": key}, raise_on_error=False)
            assert result.is_error is True
            assert result.structured_content is None
            guidance = result.meta["computerlove.tech/umbod"]["guidance"]
            assert guidance["error"]["code"] == "reporting_disabled"
            assert guidance["recovery"]["retry"] == "never"
            assert guidance["operation_state"] == "not_started"
        assert (await client.call_tool("unrelated_tool", {})).data == "available"

    page = await service.list_reports(ReportQuery())
    assert page.total == 1
    assert str(page.items[0].report_id) == receipt.structured_content["report_id"]


@pytest.mark.asyncio
async def test_mcp_discovery_omits_dormant_patterns_and_hides_capabilities_when_all_are_removed(default_diagnostic_mcp: DiagnosticMcp) -> None:
    service = default_diagnostic_mcp.service
    defaults = await service.get_configuration()
    patterns = tuple(pattern.model_copy(update={"enabled": False}) if pattern.id == "missing-context" else pattern for pattern in defaults.patterns)
    await service.publish_configuration(PublishConfiguration(
        expected_revision=1, reporting_enabled=True, patterns=patterns, playbooks=defaults.playbooks,
    ))
    async with Client(default_diagnostic_mcp.server) as client:
        instructions = json.loads((await client.read_resource(INSTRUCTIONS))[0].text)
        assert instructions["playbook"]["pattern_ids"] == ["tool-problems", "task-blocked", "user-correction"]
        assert len(instructions["patterns"]) == 3
        await service.publish_configuration(PublishConfiguration(
            expected_revision=2, reporting_enabled=True, patterns=(), playbooks=defaults.playbooks,
        ))
        assert await client.list_tools() == []
        assert await client.list_resource_templates() == []
        assert (await service.get_configuration()).playbooks == defaults.playbooks
