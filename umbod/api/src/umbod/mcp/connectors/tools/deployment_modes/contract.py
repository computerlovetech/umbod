from collections.abc import Callable
from typing import Literal, Protocol

from fastmcp import FastMCP

from umbod.core.connectors.native.runtime.tools import ConnectorToolMapping
from umbod.mcp.connectors.tools.infrastructure.client_notifications import (
    ToolListChangedClientNotifier,
)
from umbod.mcp.connectors.tools.runtime.ports import ConnectorToolExposureStrategy
from umbod.mcp.connectors.tools.invocation.ports import ConnectorToolInvoker
from umbod.mcp.connectors.tools.runtime.registry import RuntimeConnectorToolRegistry

ConnectorToolExposureMode = Literal["flat", "gateway", "codemode"]


class ConnectorToolDeploymentFactory(Protocol):
    def create_exposure_strategy(
        self,
        mcp: FastMCP,
        invoker_factory: Callable[[ConnectorToolMapping], ConnectorToolInvoker],
        client_notifier: ToolListChangedClientNotifier,
    ) -> ConnectorToolExposureStrategy: ...

    def register_fixed_tools(
        self,
        mcp: FastMCP,
        registry: RuntimeConnectorToolRegistry,
    ) -> None: ...
