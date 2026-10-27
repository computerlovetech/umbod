from uuid import UUID, uuid4

from umbod.core.caching import AsyncRequestCache
from umbod.core.publishing.store import ConnectorPublicationReader


class CachedConnectorPublicationReader(ConnectorPublicationReader):
    def __init__(
        self,
        reader: ConnectorPublicationReader,
        cache: AsyncRequestCache[tuple[UUID, str, str], bool],
    ) -> None:
        self._reader = reader
        self._cache = cache
        self._namespace = uuid4()

    async def is_published(self, connector_id: str) -> bool:
        async def load() -> bool:
            return await self._reader.is_published(connector_id)

        return await self._cache.get_or_load(
            (self._namespace, "is_published", connector_id), load,
        )

    async def was_previously_published(self, connector_id: str) -> bool:
        async def load() -> bool:
            return await self._reader.was_previously_published(connector_id)

        return await self._cache.get_or_load(
            (self._namespace, "was_previously_published", connector_id), load,
        )
