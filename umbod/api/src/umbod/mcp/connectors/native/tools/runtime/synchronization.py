from umbod.core.capabilities.tools.refs import ConnectorToolRef
from umbod.core.connectors.native.tools.runtime_state import ConnectorToolRuntimeState
from umbod.mcp.connectors.native.tools.runtime.ports import RuntimeReconciliationResult, RuntimeStateReader, RuntimeStateReconciler, RuntimeStateStore


class ConnectorToolRuntimeStateSynchronizer:
    def __init__(
        self,
        *,
        reader: RuntimeStateReader[ConnectorToolRef, ConnectorToolRuntimeState],
        store: RuntimeStateStore[ConnectorToolRef, ConnectorToolRuntimeState],
        reconciler: RuntimeStateReconciler[ConnectorToolRef],
    ) -> None:
        self._reader = reader
        self._store = store
        self._reconciler = reconciler

    async def sync_runtime_state(self, key: ConnectorToolRef) -> RuntimeReconciliationResult:
        state = await self._reader.get_runtime_state(key)
        if state is None:
            self._store.delete_runtime_state(key)
        else:
            self._store.save_runtime_state(state)
        return await self._reconciler.reconcile_runtime_state(key)
