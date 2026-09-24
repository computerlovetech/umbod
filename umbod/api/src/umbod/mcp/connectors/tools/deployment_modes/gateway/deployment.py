from collections.abc import Callable

from fastmcp import FastMCP

from umbod.core.connectors.native.runtime.tools import ConnectorToolMapping
from umbod.mcp.connectors.tools.infrastructure.client_notifications import (
    ToolListChangedClientNotifier,
)
from umbod.mcp.connectors.tools.runtime.ports import ConnectorToolExposureStrategy
from umbod.mcp.connectors.tools.deployment_modes.gateway.exposure import (
    GatewayConnectorToolExposureStrategy,
)
from umbod.mcp.connectors.tools.deployment_modes.gateway.tools import (
    GATEWAY_SEARCH_DESCRIPTION,
    register_connector_execute_tool,
)
from umbod.mcp.connectors.tools.discovery.tools import register_connector_search_tool
from umbod.mcp.connectors.tools.invocation.ports import ConnectorToolInvoker
from umbod.mcp.connectors.tools.runtime.registry import RuntimeConnectorToolRegistry
from umbod.mcp.connectors.tools.discovery.search import InMemoryFuzzyConnectorToolSearch


class GatewayConnectorToolDeploymentFactory:
    def create_exposure_strategy(
        self,
        mcp: FastMCP,
        invoker_factory: Callable[[ConnectorToolMapping], ConnectorToolInvoker],
        client_notifier: ToolListChangedClientNotifier,
    ) -> ConnectorToolExposureStrategy:
        return GatewayConnectorToolExposureStrategy(client_notifier)

    def register_fixed_tools(
        self,
        mcp: FastMCP,
        registry: RuntimeConnectorToolRegistry,
    ) -> None:
        setattr(mcp, "connector_tool_search", InMemoryFuzzyConnectorToolSearch())
        register_connector_search_tool(mcp, GATEWAY_SEARCH_DESCRIPTION)
        register_connector_execute_tool(mcp)
