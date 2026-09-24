from collections.abc import Sequence
from dataclasses import dataclass
from typing import Generic, Protocol, TypeVar

from umbod.core.connectors.native.runtime.tools import ConnectorToolMapping

StateKeyT = TypeVar("StateKeyT")
StateT = TypeVar("StateT")


@dataclass(frozen=True)
class RuntimeReconciliationResult:
    resource_name: str
    visible_before: bool
    visible_after: bool
    clients_notified: bool = True


class RuntimeStateReader(Protocol, Generic[StateKeyT, StateT]):
    async def get_runtime_state(self, key: StateKeyT) -> StateT | None: ...


class RuntimeStateStore(Protocol, Generic[StateKeyT, StateT]):
    def save_runtime_state(self, state: StateT) -> None: ...

    def delete_runtime_state(self, key: StateKeyT) -> None: ...


class RuntimeStateReconciler(Protocol, Generic[StateKeyT]):
    def reconcile_runtime_state(self, key: StateKeyT) -> RuntimeReconciliationResult: ...


class ConnectorToolExposureLifecycle(Protocol):
    def remove_tool(self, tool_name: str) -> None: ...


class ConnectorToolExposureStrategy(Protocol):
    def reconcile_connector(
        self,
        connector_id: str,
        eligible_mappings: Sequence[ConnectorToolMapping],
    ) -> None: ...

    def reconcile_runtime_state(
        self,
        connector_id: str,
        tool_name: str,
        eligible_mappings: Sequence[ConnectorToolMapping],
    ) -> RuntimeReconciliationResult: ...
