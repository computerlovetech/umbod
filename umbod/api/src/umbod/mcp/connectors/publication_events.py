import asyncio
import json

from collections.abc import Awaitable, Callable
from typing import Protocol
from urllib.parse import urlencode
from urllib.request import urlopen

from pydantic import TypeAdapter

from umbod.core.capabilities.descriptions.events import ConnectorCapabilityDescriptionOverrideChangedStreamEvent
from umbod.core.publishing.events import ConnectorPublicationStreamEvent
from umbod.core.configuration.events import ConnectorRuntimeStateStreamEvent
from messaging.models import StreamEvent
from umbod.core.publishing.events import ConnectorPublicationEventCheckpointStore


class ConnectorPublicationStreamReader(Protocol):
    async def list_after(
        self, sequence: int, limit: int
    ) -> list[ConnectorPublicationStreamEvent]: ...


class ConnectorCapabilityDescriptionOverrideStreamReader(Protocol):
    async def list_after(
        self, sequence: int, limit: int
    ) -> list[ConnectorCapabilityDescriptionOverrideChangedStreamEvent]: ...


class ConnectorRuntimeStateStreamReader(Protocol):
    async def list_after(
        self, sequence: int, limit: int
    ) -> list[ConnectorRuntimeStateStreamEvent]: ...


ConnectorPublicationEventHandler = Callable[[str], Awaitable[None] | None]
ConnectorRuntimeStateEventHandler = Callable[[str], Awaitable[None] | None]
CONNECTOR_PUBLICATION_POLLING_INTERVAL_SECONDS = 5.0
CONNECTOR_PUBLICATION_POLLING_BATCH_LIMIT = 100


class HttpConnectorPublicationStreamReader:
    def __init__(self, api_base_url: str) -> None:
        self._api_base_url = api_base_url.rstrip("/")
        self._events_adapter = TypeAdapter(list[StreamEvent])

    async def list_after(self, sequence: int, limit: int) -> list[ConnectorPublicationStreamEvent]:
        return await asyncio.to_thread(self._list_after_sync, sequence, limit)

    def _list_after_sync(self, sequence: int, limit: int) -> list[ConnectorPublicationStreamEvent]:
        query = urlencode(
            {
                "after_sequence": sequence,
                "limit": limit,
                "event_type": "connector.publication.changed",
            }
        )
        url = f"{self._api_base_url}/system/events?{query}"
        with urlopen(url, timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8"))
        return [
            ConnectorPublicationStreamEvent.from_stream_event(event)
            for event in self._events_adapter.validate_python(payload)
        ]


class HttpConnectorCapabilityDescriptionOverrideStreamReader:
    def __init__(self, api_base_url: str) -> None:
        self._api_base_url = api_base_url.rstrip("/")
        self._events_adapter = TypeAdapter(list[StreamEvent])

    async def list_after(self, sequence: int, limit: int) -> list[ConnectorCapabilityDescriptionOverrideChangedStreamEvent]:
        return await asyncio.to_thread(self._list_after_sync, sequence, limit)

    def _list_after_sync(self, sequence: int, limit: int) -> list[ConnectorCapabilityDescriptionOverrideChangedStreamEvent]:
        query = urlencode({"after_sequence": sequence, "limit": limit, "event_type": "connector.capability_description_override.changed"})
        with urlopen(f"{self._api_base_url}/system/events?{query}", timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8"))
        return [ConnectorCapabilityDescriptionOverrideChangedStreamEvent.from_stream_event(event) for event in self._events_adapter.validate_python(payload)]


class HttpConnectorRuntimeStateStreamReader:
    def __init__(self, api_base_url: str) -> None:
        self._api_base_url = api_base_url.rstrip("/")
        self._events_adapter = TypeAdapter(list[StreamEvent])

    async def list_after(self, sequence: int, limit: int) -> list[ConnectorRuntimeStateStreamEvent]:
        return await asyncio.to_thread(self._list_after_sync, sequence, limit)

    def _list_after_sync(self, sequence: int, limit: int) -> list[ConnectorRuntimeStateStreamEvent]:
        query = urlencode(
            {
                "after_sequence": sequence,
                "limit": limit,
                "event_type": "connector.configuration.changed",
            }
        )
        url = f"{self._api_base_url}/system/events?{query}"
        with urlopen(url, timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8"))
        return [
            ConnectorRuntimeStateStreamEvent.from_stream_event(event)
            for event in self._events_adapter.validate_python(payload)
        ]


class ConnectorPublicationPollingSynchronizer:
    def __init__(
        self,
        *,
        consumer_id: str,
        checkpoint_store: ConnectorPublicationEventCheckpointStore,
        stream_reader: ConnectorPublicationStreamReader,
        handler: ConnectorPublicationEventHandler,
        interval_seconds: float,
        batch_limit: int,
    ) -> None:
        self._delegate = ConnectorRuntimeStateChangePollingSynchronizer(
            consumer_id=consumer_id,
            checkpoint_store=checkpoint_store,
            stream_reader=stream_reader,
            handler=handler,
            interval_seconds=interval_seconds,
            batch_limit=batch_limit,
        )

    async def poll_once(self) -> None:
        await self._delegate.poll_once()

    async def run(self) -> None:
        await self._delegate.run()

    def stop(self) -> None:
        self._delegate.stop()


class ConnectorRuntimeStateChangePollingSynchronizer:
    def __init__(
        self,
        *,
        consumer_id: str,
        checkpoint_store: ConnectorPublicationEventCheckpointStore,
        stream_reader: ConnectorRuntimeStateStreamReader,
        handler: ConnectorRuntimeStateEventHandler,
        interval_seconds: float,
        batch_limit: int,
    ) -> None:
        self._consumer_id = consumer_id
        self._checkpoint_store = checkpoint_store
        self._stream_reader = stream_reader
        self._handler = handler
        self._interval_seconds = interval_seconds
        self._batch_limit = batch_limit
        self._stopped = asyncio.Event()

    async def poll_once(self) -> None:
        sequence = await self._checkpoint_store.get_last_processed_sequence(self._consumer_id)
        events = await self._stream_reader.list_after(sequence, self._batch_limit)
        for stream_event in events:
            result = self._handler(stream_event.event.connector_id)
            if result is not None:
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
