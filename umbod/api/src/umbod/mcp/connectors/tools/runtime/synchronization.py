import asyncio
import inspect

from collections.abc import Awaitable, Callable
from typing import Protocol

from umbod.core.capabilities.tools.refs import ConnectorToolRef
from umbod.core.connectors.native.tools.runtime_state import ConnectorToolRuntimeState
from umbod.core.activation.events import ConnectorCapabilityActivationChanged, ConnectorToolChangedStreamEvent

from umbod.mcp.connectors.tools.runtime.ports import (
    RuntimeReconciliationResult,
    RuntimeStateReader,
    RuntimeStateReconciler,
    RuntimeStateStore,
)

DEFAULT_POLL_INTERVAL_SECONDS = 5.0
DEFAULT_BATCH_LIMIT = 100

ConnectorToolChangeEventHandler = Callable[
    [ConnectorCapabilityActivationChanged], Awaitable[object] | object
]


class ConnectorToolChangeEventCheckpointStore(Protocol):
    async def get_last_processed_sequence(self, consumer_id: str) -> int: ...

    async def save_last_processed_sequence(self, consumer_id: str, sequence: int) -> None: ...


class ConnectorToolChangeStreamReader(Protocol):
    async def list_after(
        self, sequence: int, limit: int
    ) -> list[ConnectorToolChangedStreamEvent]: ...


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


class ConnectorToolChangePollingSynchronizer:
    def __init__(
        self,
        *,
        consumer_id: str,
        checkpoint_store: ConnectorToolChangeEventCheckpointStore,
        stream_reader: ConnectorToolChangeStreamReader,
        handler: ConnectorToolChangeEventHandler,
        **options: object,
    ) -> None:
        self._consumer_id = consumer_id
        self._checkpoint_store = checkpoint_store
        self._stream_reader = stream_reader
        self._handler = handler
        self._interval_seconds = self._resolve_interval_seconds(options)
        self._batch_limit = self._resolve_batch_limit(options)
        self._stopped = asyncio.Event()

    def _resolve_interval_seconds(self, options: dict[str, object]) -> float:
        interval_seconds = options.pop("interval_seconds", DEFAULT_POLL_INTERVAL_SECONDS)
        if not isinstance(interval_seconds, (int, float)):
            raise TypeError("interval_seconds must be a number")
        return float(interval_seconds)

    def _resolve_batch_limit(self, options: dict[str, object]) -> int:
        batch_limit = options.pop("batch_limit", DEFAULT_BATCH_LIMIT)
        if options:
            unexpected_option = next(iter(options))
            raise TypeError(f"Unexpected option: {unexpected_option}")
        if not isinstance(batch_limit, int):
            raise TypeError("batch_limit must be an int")
        return batch_limit

    async def poll_once(self) -> None:
        sequence = await self._checkpoint_store.get_last_processed_sequence(self._consumer_id)
        events = await self._stream_reader.list_after(sequence, self._batch_limit)
        for stream_event in events:
            result = self._handler(stream_event.event)
            if inspect.isawaitable(result):
                await result
            await self._checkpoint_store.save_last_processed_sequence(
                self._consumer_id, stream_event.sequence
            )

    async def run(self) -> None:
        while not self._stopped.is_set():
            try:
                await self.poll_once()
            except Exception:
                pass
            try:
                await asyncio.wait_for(self._stopped.wait(), timeout=self._interval_seconds)
            except TimeoutError:
                pass

    def stop(self) -> None:
        self._stopped.set()
