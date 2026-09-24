from umbod.core.publishing.events import ConnectorPublicationChanged, ConnectorPublicationStreamEvent
from umbod.core.configuration.events import ConnectorRuntimeStateChanged, ConnectorRuntimeStateStreamEvent
from umbod.core.activation.events import ConnectorToolChanged, ConnectorToolChangedStreamEvent
from messaging.ports import EventCheckpointStore, EventStream


class ConnectorPublicationEventStreamAdapter:
    def __init__(self, stream: EventStream) -> None:
        self._stream = stream

    async def append_connector_publication_changed(
        self, event: ConnectorPublicationChanged
    ) -> ConnectorPublicationStreamEvent:
        validated_event = ConnectorPublicationChanged.model_validate(event)
        stream_event = await self._stream.append(validated_event.to_messaging_event())
        return ConnectorPublicationStreamEvent.from_stream_event(stream_event)

    async def list_connector_publication_changed_after(
        self, sequence: int, limit: int
    ) -> list[ConnectorPublicationStreamEvent]:
        events = await self._stream.list_after(sequence, limit)
        return [ConnectorPublicationStreamEvent.from_stream_event(event) for event in events]

    async def close(self) -> None:
        await self._stream.close()


class ConnectorRuntimeStateEventStreamAdapter:
    def __init__(self, stream: EventStream) -> None:
        self._stream = stream

    async def append_connector_runtime_state_changed(
        self, event: ConnectorRuntimeStateChanged
    ) -> ConnectorRuntimeStateStreamEvent:
        validated_event = ConnectorRuntimeStateChanged.model_validate(event)
        stream_event = await self._stream.append(validated_event.to_messaging_event())
        return ConnectorRuntimeStateStreamEvent.from_stream_event(stream_event)

    async def list_connector_runtime_state_changed_after(
        self, sequence: int, limit: int
    ) -> list[ConnectorRuntimeStateStreamEvent]:
        events = await self._stream.list_after(sequence, limit)
        return [ConnectorRuntimeStateStreamEvent.from_stream_event(event) for event in events]

    async def close(self) -> None:
        await self._stream.close()


class ConnectorToolChangeEventStreamAdapter:
    def __init__(self, stream: EventStream) -> None:
        self._stream = stream

    async def append_connector_tool_changed(
        self, event: ConnectorToolChanged
    ) -> ConnectorToolChangedStreamEvent:
        validated_event = ConnectorToolChanged.model_validate(event)
        stream_event = await self._stream.append(validated_event.to_messaging_event())
        return ConnectorToolChangedStreamEvent.from_stream_event(stream_event)

    async def list_connector_tool_changed_after(
        self, sequence: int, limit: int
    ) -> list[ConnectorToolChangedStreamEvent]:
        events = await self._stream.list_after(sequence, limit)
        return [ConnectorToolChangedStreamEvent.from_stream_event(event) for event in events]

    async def close(self) -> None:
        await self._stream.close()


class ConnectorEventCheckpointStoreAdapter:
    def __init__(self, store: EventCheckpointStore) -> None:
        self._store = store

    async def get_last_processed_sequence(self, consumer_id: str) -> int:
        return await self._store.get_last_processed_sequence(consumer_id)

    async def save_last_processed_sequence(self, consumer_id: str, sequence: int) -> None:
        await self._store.save_last_processed_sequence(consumer_id, sequence)

    async def close(self) -> None:
        await self._store.close()
