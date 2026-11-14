import json

import pytest
from fastmcp import Client

from umbod.core.agent_behaviour import PublishConfiguration, ReportQuery

from .conftest import DiagnosticMcp


@pytest.mark.asyncio
async def test_stable_resource_resolves_new_publication_without_restart(diagnostic_mcp: DiagnosticMcp) -> None:
    async with Client(diagnostic_mcp.server) as client:
        first = json.loads((await client.read_resource("umbod://agent-behaviour/playbooks/review"))[0].text)
        current = await diagnostic_mcp.service.get_configuration()
        await diagnostic_mcp.service.publish_configuration(PublishConfiguration(
            expected_revision=current.revision, patterns=current.patterns,
            playbooks=(current.playbooks[0].model_copy(update={"collection_instructions": "New authorized review"}),),
        ))
        second = json.loads((await client.read_resource("umbod://agent-behaviour/playbooks/review"))[0].text)
    assert first["configuration_revision"] == 2
    assert second["configuration_revision"] == 3
    assert second["playbook"]["collection_instructions"] == "New authorized review"
    assert second["reporting_guidance"] == first["reporting_guidance"]
    assert (await diagnostic_mcp.service.list_reports(ReportQuery())).total == 0


@pytest.mark.asyncio
async def test_empty_enabled_index_preserves_eligible_capability_discovery(diagnostic_mcp: DiagnosticMcp) -> None:
    current = await diagnostic_mcp.service.get_configuration()
    await diagnostic_mcp.service.publish_configuration(PublishConfiguration(
        expected_revision=current.revision, patterns=current.patterns,
        playbooks=(current.playbooks[0].model_copy(update={"enabled": False}),),
    ))
    async with Client(diagnostic_mcp.server) as client:
        assert [tool.name for tool in await client.list_tools()] == ["report_diagnostic"]
        index = json.loads((await client.read_resource("umbod://agent-behaviour/playbooks"))[0].text)
        assert index == {"configuration_revision": 3, "playbooks": []}
        for playbook in ["review", "missing"]:
            with pytest.raises(Exception, match="instructions_unavailable"):
                await client.read_resource(f"umbod://agent-behaviour/playbooks/{playbook}")
            with pytest.raises(Exception, match="instructions_unavailable"):
                await client.get_prompt("run_diagnostics", {"playbook_id": playbook})
