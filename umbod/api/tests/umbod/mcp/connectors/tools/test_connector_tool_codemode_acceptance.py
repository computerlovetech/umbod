from tests.support.native_tool_states import enabled_native_tool_states
from typing import Any

from umbod.mcp.listeners import create_mcp_signals
from umbod.mcp.signals.execution import SignalToolExecutionPipelineFactory
from umbod.mcp.metrics import PrometheusMcpMetricsRecorder
from umbod.mcp.logging import create_default_mcp_audit_recorder

import pytest
from fastmcp import FastMCP

from tests.support.configuration import InMemoryConnectorCurrentConfigurationStore
from umbod.core.invocation import PermitAllConnectorInvocationPolicy
from umbod.mcp.connectors.native.tools import register_connector_tools
from umbod.mcp.logging import create_default_mcp_tool_invocation_log_sink
from tests.umbod.mcp.connectors.tools.test_connector_tool_exposure_mode_acceptance import InMemoryConnectorPublishingStore
from tests.umbod.mcp.connectors.tools.codemode_acceptance import ConnectorCodeMode


@pytest.mark.asyncio
async def test_codemode_exposes_conventional_and_openapi_discovery_without_openapi_execution() -> (
    None
):
    agent = await ConnectorCodeMode().running()

    tool_names = await agent.list_tool_names()

    assert tool_names == {"search_tools", "execute_code"} | {"filesystem_browse", "get_filesystem_root", "get_filesystem_node", "list_filesystem_children", "create_filesystem_file", "create_filesystem_directory", "filesystem_upload", "filesystem_delete_file", "filesystem_read_file", "filesystem_list_sharing_groups", "filesystem_share"}
    assert "execute_openapi_capability" not in tool_names


@pytest.mark.asyncio
async def test_codemode_instructs_agents_to_discover_external_capabilities() -> None:
    agent = await ConnectorCodeMode().running()

    descriptions = await agent.list_tool_descriptions()

    assert "whenever a request may require an external service" in descriptions["search_tools"]
    assert "Search by the user's goal and domain" in descriptions["search_tools"]
    assert "Before writing code, use search_tools" in descriptions["execute_code"]
    assert "follow each input_schema" in descriptions["execute_code"]


@pytest.mark.asyncio
async def test_codemode_registration_does_not_mutate_unrelated_tools() -> None:
    mcp = FastMCP("codemode-test")

    @mcp.tool
    def unrelated_tool() -> dict[str, str]:
        return {"status": "still callable"}

    signals = create_mcp_signals(create_default_mcp_tool_invocation_log_sink(), PrometheusMcpMetricsRecorder(), create_default_mcp_audit_recorder("test"))
    await register_connector_tools(
        mcp,
        signals=signals,
        execution_pipelines=SignalToolExecutionPipelineFactory(signals, PermitAllConnectorInvocationPolicy()),
        connector_registrations=[],
        connector_configuration_store=InMemoryConnectorCurrentConfigurationStore(),
        connector_publishing_store=InMemoryConnectorPublishingStore(),
        connector_tool_mappings=[],
        connector_tool_runtime_state_store=enabled_native_tool_states(),
        connector_tool_exposure_mode="codemode",
    )

    tool_names = {tool.name for tool in await mcp.list_tools()}
    result = await mcp.call_tool("unrelated_tool", {})

    assert {"unrelated_tool", "search_tools", "execute_code"} <= tool_names
    assert result.structured_content == {"status": "still callable"}


@pytest.mark.asyncio
async def test_codemode_reuses_authorized_connector_search() -> None:
    agent = await ConnectorCodeMode().running()

    matches = await agent.search("readable channels")

    assert {match["tool_name"] for match in matches} == {"slack_list_readable_channels"}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("code", "final_value", "printed_output", "call_count"),
    [
        ("slack_list_readable_channels(limit=5)", {"arguments": {"limit": 5}}, "", 1),
        (
            "first = slack_list_readable_channels(limit=1)\nslack_list_readable_channels(limit=2)",
            {"arguments": {"limit": 2}},
            "",
            2,
        ),
        (
            "values = [slack_list_readable_channels(limit=i) for i in range(2)]\nvalues",
            [{"arguments": {"limit": 0}}, {"arguments": {"limit": 1}}],
            "",
            2,
        ),
        ("print('ready')\n6 * 7", 42, "ready\n", 0),
        ("print()\n6 * 7", 42, "\n", 0),
        ("print('done')", None, "done\n", 0),
    ],
)
async def test_code_composes_operations_with_python_semantics(
    code: str,
    final_value: Any,
    printed_output: str,
    call_count: int,
) -> None:
    codemode = ConnectorCodeMode()
    agent = await codemode.running()

    result = await agent.execute(code)

    assert result.outcome == "success"
    assert result.final_value == final_value
    assert result.printed_output == printed_output
    assert len(result.nested_calls) == call_count


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "code",
    [
        "if :",
        "missing_connector_operation()",
        "open('/etc/passwd').read()",
        "import os\nos.environ",
        "import socket",
        "import subprocess",
        "import time\ntime.time()",
    ],
)
async def test_code_failures_do_not_escape_the_sandbox(code: str) -> None:
    codemode = ConnectorCodeMode()
    agent = await codemode.running()

    result = await agent.execute(code)

    assert result.outcome == "failure"
    assert result.error
    assert codemode.invocations == []


@pytest.mark.asyncio
async def test_uncaught_nested_failure_stops_later_calls_and_retains_evidence() -> None:
    codemode = ConnectorCodeMode()
    agent = await codemode.running()

    result = await agent.execute(
        "slack_list_readable_channels(limit=1)\n"
        "slack_list_readable_channels(limit='invalid')\n"
        "slack_list_readable_channels(limit=3)"
    )

    assert result.outcome == "failure"
    assert [call["outcome"] for call in result.nested_calls] == ["success", "failure"]
    assert codemode.invocations == [{"limit": 1}]


@pytest.mark.asyncio
async def test_each_execution_has_fresh_state() -> None:
    agent = await ConnectorCodeMode().running()

    first = await agent.execute("remembered = 42\nremembered")
    second = await agent.execute("remembered")

    assert first.outcome == "success"
    assert second.outcome == "failure"


@pytest.mark.asyncio
async def test_code_execution_reports_server_timeout() -> None:
    agent = await ConnectorCodeMode().running(timeout_seconds=0.01)

    result = await agent.execute("while True:\n    pass")

    assert result.outcome == "timeout"
    assert result.error
    assert result.nested_calls == []


def test_codemode_defaults_to_thirty_second_server_timeout() -> None:
    settings = ConnectorCodeMode().startup_settings()

    assert settings.mcp.connector_code_execution_timeout_seconds == 30


def test_codemode_accepts_server_timeout_override_only() -> None:
    settings = ConnectorCodeMode().startup_settings(timeout_seconds=0.25)

    assert settings.mcp.connector_code_execution_timeout_seconds == 0.25
