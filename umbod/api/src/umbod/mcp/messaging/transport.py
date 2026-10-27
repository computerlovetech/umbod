import asyncio
import json
from typing import Literal
from urllib.parse import urlencode
from urllib.request import urlopen

from pydantic import TypeAdapter

from messaging.in_memory import InMemoryEventCheckpointStoreFactory, InMemoryEventCheckpointStoreMessages
from messaging.models import StreamEvent
from messaging.ports import EventCheckpointStore
from umbod.core.messaging import DatabaseEventStream
from umbod.core.persistence import Database
from umbod.mcp.messaging.projection import ProjectionEventReader


class HttpProjectionEventReader:
    def __init__(self, api_base_url: str) -> None:
        self._base_url = api_base_url.rstrip('/')

    async def list_after(self, sequence: int, limit: int) -> list[StreamEvent]:
        return await asyncio.to_thread(self._list_after, sequence, limit)

    def _list_after(self, sequence: int, limit: int) -> list[StreamEvent]:
        query = urlencode({'after_sequence': sequence, 'limit': limit})
        with urlopen(f'{self._base_url}/system/events?{query}', timeout=10) as response:
            return TypeAdapter(list[StreamEvent]).validate_python(json.loads(response.read()))


class DatabaseProjectionEventReader:
    def __init__(self, database: Database) -> None:
        self._stream = DatabaseEventStream(database)

    async def list_after(self, sequence: int, limit: int) -> list[StreamEvent]:
        return await self._stream.list_after_types(sequence, limit, (
            'connector.publication.changed',
            'connector.configuration.changed',
            'connector.capability_activation.changed',
            'connector.capability_description_override.changed',
            'connector.discovery.changed',
            'mcp.group_permission.changed',
        ))


class McpMessagingAdapterFactory:
    def __init__(self, transport: Literal['http', 'sql'], api_base_url: str, database: Database) -> None:
        self._transport = transport
        self._api_base_url = api_base_url
        self._database = database

    def create_checkpoint_store(self) -> EventCheckpointStore:
        return InMemoryEventCheckpointStoreFactory(InMemoryEventCheckpointStoreMessages()).create()

    def create_projection_reader(self) -> ProjectionEventReader:
        if self._transport == 'sql':
            return DatabaseProjectionEventReader(self._database)
        return HttpProjectionEventReader(self._api_base_url)
