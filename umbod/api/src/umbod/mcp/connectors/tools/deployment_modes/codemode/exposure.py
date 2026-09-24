from collections.abc import Sequence

from umbod.core.connectors.native.runtime.tools import ConnectorToolMapping
from umbod.mcp.connectors.tools.definition.naming import _tool_name
from umbod.mcp.connectors.tools.infrastructure.client_notifications import (
    ToolListChangedClientNotifier,
)
from umbod.mcp.connectors.tools.runtime.ports import RuntimeReconciliationResult


class CodeModeConnectorToolExposureStrategy:
    def __init__(self, client_notifier: ToolListChangedClientNotifier) -> None:
        self._client_notifier = client_notifier
        self._visible_tool_names_by_connector_id: dict[str, set[str]] = {}

    def reconcile_connector(
        self,
        connector_id: str,
        eligible_mappings: Sequence[ConnectorToolMapping],
    ) -> None:
        eligible_tool_names = {_tool_name(mapping) for mapping in eligible_mappings}
        visible_tool_names = self._visible_tool_names(connector_id)
        self._visible_tool_names_by_connector_id[connector_id] = eligible_tool_names
        if visible_tool_names != eligible_tool_names:
            self._client_notifier.notify_tool_list_changed()

    def reconcile_runtime_state(
        self,
        connector_id: str,
        tool_name: str,
        eligible_mappings: Sequence[ConnectorToolMapping],
    ) -> RuntimeReconciliationResult:
        visible_before = tool_name in self._visible_tool_names(connector_id)
        self.reconcile_connector(connector_id, eligible_mappings)
        visible_after = tool_name in self._visible_tool_names(connector_id)
        return RuntimeReconciliationResult(
            resource_name=tool_name,
            visible_before=visible_before,
            visible_after=visible_after,
            clients_notified=True,
        )

    def _visible_tool_names(self, connector_id: str) -> set[str]:
        if connector_id not in self._visible_tool_names_by_connector_id:
            return set()
        return self._visible_tool_names_by_connector_id[connector_id]

