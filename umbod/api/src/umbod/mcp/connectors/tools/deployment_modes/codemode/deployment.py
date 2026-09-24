from collections.abc import Callable

from fastmcp import FastMCP

from umbod.core.connectors.native.runtime.tools import ConnectorToolMapping
from umbod.mcp.connectors.tools.infrastructure.client_notifications import (
    ToolListChangedClientNotifier,
)
from umbod.mcp.connectors.tools.deployment_modes.codemode.tools import (
    CODEMODE_SEARCH_DESCRIPTION,
    register_connector_code_mode_tool,
)
from umbod.mcp.connectors.tools.runtime.ports import ConnectorToolExposureStrategy
from umbod.mcp.connectors.tools.deployment_modes.codemode.exposure import (
    CodeModeConnectorToolExposureStrategy,
)
from umbod.mcp.connectors.tools.discovery.tools import register_connector_search_tool
from umbod.mcp.connectors.tools.invocation.ports import ConnectorToolInvoker
from umbod.mcp.connectors.tools.runtime.registry import RuntimeConnectorToolRegistry
from umbod.mcp.connectors.tools.discovery.search import InMemoryFuzzyConnectorToolSearch


class CodeModeConnectorToolDeploymentFactory:
    def __init__(self, code_execution_timeout_seconds: float) -> None:
        self._code_execution_timeout_seconds = code_execution_timeout_seconds

    def create_exposure_strategy(
        self,
        mcp: FastMCP,
        invoker_factory: Callable[[ConnectorToolMapping], ConnectorToolInvoker],
        client_notifier: ToolListChangedClientNotifier,
    ) -> ConnectorToolExposureStrategy:
        return CodeModeConnectorToolExposureStrategy(client_notifier)

    def register_fixed_tools(
        self,
        mcp: FastMCP,
        registry: RuntimeConnectorToolRegistry,
    ) -> None:
        setattr(mcp, "connector_tool_search", InMemoryFuzzyConnectorToolSearch())
        register_connector_search_tool(mcp, CODEMODE_SEARCH_DESCRIPTION)
        register_connector_code_mode_tool(
            mcp,
            registry,
            self._code_execution_timeout_seconds,
        )
