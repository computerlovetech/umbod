from collections.abc import Callable

from fastmcp import FastMCP

from umbod.core.connectors.native.runtime.tools import ConnectorToolMapping
from umbod.mcp.connectors.tools.infrastructure.client_notifications import (
    ToolListChangedClientNotifier,
)
from umbod.mcp.connectors.tools.definition.registrar import FastMcpConnectorToolRegistrar
from umbod.mcp.connectors.tools.file_app import ConnectorFileAppRegistration
from umbod.mcp.connectors.tools.runtime.ports import ConnectorToolExposureStrategy
from umbod.mcp.connectors.tools.deployment_modes.flat.exposure import (
    FastMcpConnectorToolExposureLifecycle,
    FlatConnectorToolExposureStrategy,
)
from umbod.mcp.connectors.tools.invocation.ports import ConnectorToolInvoker
from umbod.mcp.connectors.tools.runtime.registry import RuntimeConnectorToolRegistry


class FlatConnectorToolDeploymentFactory:
    def __init__(self, maximum_uploaded_file_bytes: int) -> None:
        self._maximum_uploaded_file_bytes = maximum_uploaded_file_bytes

    def create_exposure_strategy(
        self,
        mcp: FastMCP,
        invoker_factory: Callable[[ConnectorToolMapping], ConnectorToolInvoker],
        client_notifier: ToolListChangedClientNotifier,
    ) -> ConnectorToolExposureStrategy:
        file_app_registrations: dict[str, ConnectorFileAppRegistration] = {}
        return FlatConnectorToolExposureStrategy(
            mcp,
            FastMcpConnectorToolRegistrar(
                self._maximum_uploaded_file_bytes,
                file_app_registrations,
            ),
            invoker_factory,
            FastMcpConnectorToolExposureLifecycle(mcp, file_app_registrations),
            client_notifier,
        )

    def register_fixed_tools(
        self,
        mcp: FastMCP,
        registry: RuntimeConnectorToolRegistry,
    ) -> None:
        return None
