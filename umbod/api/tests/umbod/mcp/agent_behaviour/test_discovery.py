import json

import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError

from umbod.core.callers import AuthenticationProvenance, CallerContext, DeclaredIssuer, SubjectIdentity, UnavailableSubject
from umbod.mcp.agent_behaviour.reservations import ensure_connector_tool_name_available
from umbod.mcp.connectors.downstream_mcp.provider import reset_request_connector_scope, set_request_connector_scope

from .conftest import DiagnosticMcp


@pytest.mark.asyncio
async def test_eligible_caller_discovers_nested_report_schema_and_json_resources(diagnostic_mcp: DiagnosticMcp) -> None:
    async with Client(diagnostic_mcp.server) as client:
        tool = next(tool for tool in await client.list_tools() if tool.name == "report_diagnostic")
        assert tool.input_schema["additionalProperties"] is False
        assert tool.input_schema["properties"]["assessments"]["items"]["properties"]["status"]["enum"] == ["observed", "not_observed", "not_assessed"]
        assert set(tool.input_schema["required"]) == {"idempotency_key", "configuration_revision", "playbook_id", "trigger", "assessments"}
        assert tool.output_schema["properties"]["report_id"]["format"] == "uuid"
        assert "same UUID" in tool.description
        assert "caller-reported metadata, not permission" in tool.description
        trigger = tool.input_schema["properties"]["trigger"]
        assert trigger["enum"] == ["user_requested", "proactive"]
        assert "does not grant permission" in trigger["description"]
        assert [item.name for item in await client.list_prompts()] == ["run_diagnostics"]
        assert str((await client.list_resources())[0].uri) == "umbod://agent-behaviour/playbooks"
        assert (await client.list_resource_templates())[0].mime_type == "application/json"
        index = json.loads((await client.read_resource("umbod://agent-behaviour/playbooks"))[0].text)
        assert index == {"configuration_revision": 2, "playbooks": [{"id": "review", "name": "Review", "resource_uri": "umbod://agent-behaviour/playbooks/review"}]}


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["anonymous", "production-simulation", "connector"])
async def test_ineligible_discovery_and_direct_access_fail_closed(diagnostic_mcp: DiagnosticMcp, mode: str) -> None:
    token = set_request_connector_scope("external") if mode == "connector" else None
    if mode == "anonymous":
        diagnostic_mcp.callers.current.set(CallerContext(authentication=AuthenticationProvenance.UNAVAILABLE, subject=UnavailableSubject(kind="unavailable")))
    if mode == "production-simulation":
        diagnostic_mcp.callers.current.set(CallerContext(authentication=AuthenticationProvenance.LOCAL_SIMULATION, subject=SubjectIdentity(issuer=DeclaredIssuer(value="https://identity.invalid"), subject="alice")))
    try:
        async with Client(diagnostic_mcp.server) as client:
            assert await client.list_tools() == []
            assert await client.list_prompts() == []
            assert await client.list_resources() == []
            assert await client.list_resource_templates() == []
            with pytest.raises(Exception, match="unauthorized|not found|Unknown|authorized"):
                await client.get_prompt("run_diagnostics", {"playbook_id": "review"})
            with pytest.raises(Exception, match="unauthorized|not found|Unknown|authorized"):
                await client.read_resource("umbod://agent-behaviour/playbooks/review")
            with pytest.raises(Exception, match="unauthorized|not found|Unknown|authorized"):
                await client.call_tool("report_diagnostic", {})
    finally:
        if token is not None:
            reset_request_connector_scope(token)


@pytest.mark.parametrize("prefix,operation", [("report", "diagnostic"), ("external", "report_diagnostic")])
def test_connector_name_collision_is_reserved_in_flat_and_scoped_forms(prefix: str, operation: str) -> None:
    with pytest.raises(ToolError, match="public_tool_name_conflict"):
        ensure_connector_tool_name_available(prefix, operation)
