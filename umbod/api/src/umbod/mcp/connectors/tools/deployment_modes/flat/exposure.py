from collections.abc import Callable, Sequence

from fastmcp import FastMCP

from umbod.core.connectors.native.runtime.tools import ConnectorToolMapping
from umbod.mcp.connectors.tools.definition.naming import _tool_name
from umbod.mcp.connectors.tools.definition.registrar import ConnectorToolRegistrar
from umbod.mcp.connectors.tools.file_app import ConnectorFileAppRegistration
from umbod.mcp.connectors.tools.infrastructure.client_notifications import (
    ToolListChangedClientNotifier,
)
from umbod.mcp.connectors.tools.invocation.ports import ConnectorToolInvoker
from umbod.mcp.connectors.tools.runtime.ports import (
    ConnectorToolExposureLifecycle,
    RuntimeReconciliationResult,
)


class FastMcpConnectorToolExposureLifecycle:
    def __init__(
        self,
        mcp: FastMCP,
        file_app_registrations: dict[str, ConnectorFileAppRegistration],
    ) -> None:
        self._mcp = mcp
        self._file_app_registrations = file_app_registrations

    def remove_tool(self, tool_name: str) -> None:
        file_registration = self._file_app_registrations.get(tool_name)
        if file_registration is not None:
            file_registration.disable()
            return
        self._mcp.local_provider.remove_tool(tool_name)


class FlatConnectorToolExposureStrategy:
    def __init__(
        self,
        mcp: FastMCP,
        tool_registrar: ConnectorToolRegistrar,
        invoker_factory: Callable[[ConnectorToolMapping], ConnectorToolInvoker],
        lifecycle: ConnectorToolExposureLifecycle,
        client_notifier: ToolListChangedClientNotifier,
    ) -> None:
        self._mcp = mcp
        self._tool_registrar = tool_registrar
        self._invoker_factory = invoker_factory
        self._lifecycle = lifecycle
        self._client_notifier = client_notifier
        self._registered_tool_names_by_connector_id: dict[str, set[str]] = {}

    def reconcile_connector(
        self,
        connector_id: str,
        eligible_mappings: Sequence[ConnectorToolMapping],
    ) -> None:
        eligible_tool_names = {_tool_name(mapping) for mapping in eligible_mappings}
        registered_tool_names = self._registered_tool_names(connector_id)
        for mapping in eligible_mappings:
            tool_name = _tool_name(mapping)
            if tool_name not in registered_tool_names:
                self._tool_registrar.register(
                    self._mcp,
                    mapping,
                    self._invoker_factory(mapping),
                )
                registered_tool_names.add(tool_name)
        for tool_name in registered_tool_names - eligible_tool_names:
            self._lifecycle.remove_tool(tool_name)
            registered_tool_names.discard(tool_name)

    def reconcile_runtime_state(
        self,
        connector_id: str,
        tool_name: str,
        eligible_mappings: Sequence[ConnectorToolMapping],
    ) -> RuntimeReconciliationResult:
        visible_before = tool_name in self._registered_tool_names(connector_id)
        self.reconcile_connector(connector_id, eligible_mappings)
        visible_after = tool_name in self._registered_tool_names(connector_id)
        clients_notified = True
        if visible_before != visible_after:
            clients_notified = self._client_notifier.notify_tool_list_changed()
        return RuntimeReconciliationResult(
            resource_name=tool_name,
            visible_before=visible_before,
            visible_after=visible_after,
            clients_notified=clients_notified,
        )

    def _registered_tool_names(self, connector_id: str) -> set[str]:
        if connector_id not in self._registered_tool_names_by_connector_id:
            self._registered_tool_names_by_connector_id[connector_id] = set()
        return self._registered_tool_names_by_connector_id[connector_id]

