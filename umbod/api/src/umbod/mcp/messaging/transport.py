from typing import Callable, Generic, Literal, TypeVar

from umbod.core.capabilities.descriptions.events import ConnectorCapabilityDescriptionOverrideChangedStreamEvent
from umbod.core.publishing.events import ConnectorPublicationStreamEvent
from umbod.core.configuration.events import ConnectorRuntimeStateStreamEvent
from umbod.core.activation.events import ConnectorToolChangedStreamEvent
from umbod.core.persistence import Database
from umbod.core.messaging import DatabaseEventCheckpointStore, DatabaseEventStream
from umbod.mcp.connectors import (
    ConnectorCapabilityDescriptionOverrideStreamReader,
    ConnectorPublicationStreamReader,
    ConnectorRuntimeStateStreamReader,
    HttpConnectorCapabilityDescriptionOverrideStreamReader,
    HttpConnectorPublicationStreamReader,
    HttpConnectorRuntimeStateStreamReader,
)
from umbod.mcp.connectors.tools import (
    ConnectorToolChangeStreamReader,
    HttpConnectorToolChangeStreamReader,
)
from umbod.mcp.live_permission_updates import (
    GroupPermissionChangeStreamReader,
    HttpGroupPermissionChangeStreamReader,
)
from messaging.in_memory import (
    InMemoryEventCheckpointStoreFactory,
    InMemoryEventCheckpointStoreMessages,
)
from messaging.models import MessagingEventType, StreamEvent
from messaging.ports import EventCheckpointStore

T = TypeVar("T")


class DatabaseDomainEventReader(Generic[T]):
    def __init__(
        self,
        database: Database,
        event_type: MessagingEventType,
        mapper: Callable[[StreamEvent], T],
    ) -> None:
        self._stream = DatabaseEventStream(database)
        self._event_type = event_type
        self._mapper = mapper

    async def list_after(self, sequence: int, limit: int) -> list[T]:
        events = await self._stream.list_after_types(sequence, limit, (self._event_type,))
        return [self._mapper(event) for event in events]


class McpMessagingAdapterFactory:
    def __init__(
        self,
        transport: Literal["http", "sql"],
        api_base_url: str,
        database: Database,
    ) -> None:
        self._transport = transport
        self._api_base_url = api_base_url
        self._database = database

    def create_checkpoint_store(self) -> EventCheckpointStore:
        if self._transport == "sql":
            return DatabaseEventCheckpointStore(self._database)
        return InMemoryEventCheckpointStoreFactory(InMemoryEventCheckpointStoreMessages()).create()

    def create_publication_reader(self) -> ConnectorPublicationStreamReader:
        if self._transport == "sql":
            return DatabaseDomainEventReader(
                self._database,
                "connector.publication.changed",
                ConnectorPublicationStreamEvent.from_stream_event,
            )
        return HttpConnectorPublicationStreamReader(self._api_base_url)

    def create_runtime_state_reader(self) -> ConnectorRuntimeStateStreamReader:
        if self._transport == "sql":
            return DatabaseDomainEventReader(
                self._database,
                "connector.configuration.changed",
                ConnectorRuntimeStateStreamEvent.from_stream_event,
            )
        return HttpConnectorRuntimeStateStreamReader(self._api_base_url)

    def create_tool_activation_reader(self) -> ConnectorToolChangeStreamReader:
        if self._transport == "sql":
            return DatabaseDomainEventReader(
                self._database,
                "connector.capability_activation.changed",
                ConnectorToolChangedStreamEvent.from_stream_event,
            )
        return HttpConnectorToolChangeStreamReader(self._api_base_url)

    def create_capability_description_override_reader(
        self,
    ) -> ConnectorCapabilityDescriptionOverrideStreamReader:
        if self._transport == "sql":
            return DatabaseDomainEventReader(
                self._database,
                "connector.capability_description_override.changed",
                ConnectorCapabilityDescriptionOverrideChangedStreamEvent.from_stream_event,
            )
        return HttpConnectorCapabilityDescriptionOverrideStreamReader(self._api_base_url)

    def create_group_permission_reader(self) -> GroupPermissionChangeStreamReader:
        if self._transport == "sql":
            return DatabaseDomainEventReader(
                self._database,
                "mcp.group_permission.changed",
                lambda event: event,
            )
        return HttpGroupPermissionChangeStreamReader(self._api_base_url)
