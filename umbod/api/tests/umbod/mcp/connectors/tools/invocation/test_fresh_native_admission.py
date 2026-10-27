from collections.abc import Awaitable, Callable
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastmcp import Client, FastMCP
from pydantic import SecretStr

from umbod.core.capabilities.tools.refs import ConnectorToolRef
from umbod.core.configuration import InMemoryConnectorCurrentConfigurationStore
from umbod.core.connectors.native.runtime.tools import ConcreteConnectorToolMapping
from umbod.core.connectors.native.tools.runtime_state import ConnectorToolRuntimeState
from umbod.core.invocation import ConnectorInvocation, DirectInvocationDecision
from umbod.core.permissions import ConnectorToolPermission, InMemoryGroupConnectorToolPermissions
from umbod.mcp.connectors.native.tools import InMemoryConnectorToolRuntimeStateStore, register_connector_tools
from umbod.mcp.connectors.native.tools.infrastructure import dependencies
from umbod.mcp.signals.channels import McpSignals
from umbod.mcp.signals.execution import SignalToolExecutionPipelineFactory
from tests.support.connector_plugins import SlackAdminConfiguration


class MutablePublication:
    def __init__(self) -> None:
        self.published = True

    async def is_published(self, connector_id: str) -> bool:
        return self.published


class UnexpectedSignalFailure:
    def handles(self, name: str, error: BaseException) -> None:
        raise AssertionError(name) from error


class MutatingApprovalPolicy:
    def __init__(self, mutation: Callable[[], Awaitable[None]]) -> None:
        self._mutation = mutation
        self.calls = 0

    async def evaluate(self, invocation: ConnectorInvocation) -> DirectInvocationDecision:
        self.calls += 1
        await self._mutation()
        return DirectInvocationDecision()


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["flat", "gateway", "codemode", "retained"])
@pytest.mark.parametrize("change", ["unpublished", "disabled", "unconfigured", "revoked", "membership", "read_failure", "unchanged"])
async def test_native_rechecks_admission_after_approval_before_any_connector_io(
    monkeypatch: pytest.MonkeyPatch, mode: str, change: str,
) -> None:
    server = FastMCP("fresh-native-admission")
    configurations = InMemoryConnectorCurrentConfigurationStore()
    await configurations.save_current_configuration("slack", SlackAdminConfiguration(
        workspace_name="Workspace", bot_token=SecretStr("token"), default_channel_id="channels",
    ))
    publication = MutablePublication()
    activations = InMemoryConnectorToolRuntimeStateStore()
    key = ConnectorToolRef("slack", "list_channels")
    activations.save_runtime_state(ConnectorToolRuntimeState(key=key, status="enabled"))
    permissions = InMemoryGroupConnectorToolPermissions(group_claim_fields=("groups",))
    permissions.replace_group_permissions(
        {"engineering": ("slack",)},
        {"engineering": (ConnectorToolPermission("slack", "list_channels"),)},
    )
    server.group_connector_tool_permissions = permissions
    groups = ["engineering"]
    monkeypatch.setattr(dependencies, "get_access_token", lambda: SimpleNamespace(claims={"groups": groups}))
    monkeypatch.setattr(dependencies, "get_server", lambda: server)
    invocations: list[bool] = []

    def operation() -> dict[str, bool]:
        invocations.append(True)
        return {"executed": True}

    async def mutate_during_approval() -> None:
        if change == "unpublished":
            publication.published = False
        elif change == "disabled":
            activations.save_runtime_state(ConnectorToolRuntimeState(key=key, status="disabled"))
        elif change == "unconfigured":
            await configurations.delete_current_configuration("slack")
        elif change == "revoked":
            permissions.replace_group_permissions({"engineering": ()}, {"engineering": ()})
        elif change == "read_failure":
            monkeypatch.setattr(configurations, "get_current_configuration", AsyncMock(
                side_effect=RuntimeError("private-read-failure"),
            ))
        elif change == "membership":
            groups[:] = ["guests"]

    policy = MutatingApprovalPolicy(mutate_during_approval)
    signals = McpSignals(UnexpectedSignalFailure())
    await register_connector_tools(
        server,
        connector_registrations=[{
            "id": "slack", "display_name": "Slack", "capability_description": "Manage channels",
            "configuration_schema": SlackAdminConfiguration,
        }],
        connector_configuration_store=configurations,
        connector_publishing_store=publication,
        connector_tool_runtime_state_store=activations,
        connector_tool_mappings=[ConcreteConnectorToolMapping(
            "slack", "list_channels", "List channels", operation, {},
        )],
        signals=signals,
        execution_pipelines=SignalToolExecutionPipelineFactory(signals, policy),
        connector_tool_exposure_mode="flat" if mode == "retained" else mode,
    )
    denied = change != "unchanged"
    if mode == "retained":
        tool = await server.get_tool("slack_list_channels")
        result = await tool.run({})
        assert bool(getattr(result, "is_error", False)) is denied
    else:
        async with Client(server) as client:
            if mode == "flat":
                result = await client.call_tool("slack_list_channels", {}, raise_on_error=False)
            elif mode == "gateway":
                result = await client.call_tool("execute_tool", {
                    "tool_name": "slack_list_channels", "arguments": {},
                }, raise_on_error=False)
            else:
                result = await client.call_tool("execute_code", {
                    "code": "slack_list_channels()",
                }, raise_on_error=False)
                outcome = "failure" if denied else "success"
                assert result.structured_content["outcome"] == outcome
                assert result.structured_content["nested_calls"][0]["outcome"] == outcome
            if mode != "codemode":
                assert result.is_error is denied
    assert policy.calls == 1
    assert invocations == ([] if denied else [True])
    assert "private-read-failure" not in str(result)
    if mode != "codemode" and denied:
        assert "Connector invocation denied" in str(result)
