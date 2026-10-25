from typing import Protocol

from umbod.core.connectors.openapi.execution import AsyncStreamingHttpClient
from umbod.core.connectors.openapi.stores import OpenApiConnectorStore
from umbod.core.permissions.ports import GroupPermissionReader


class OpenApiConnectorStoreFactory(Protocol):
    async def create(self) -> OpenApiConnectorStore: ...


class GroupPermissionReaderFactory(Protocol):
    async def create(self) -> GroupPermissionReader: ...


class OutboundHttpClientFactoryPort(Protocol):
    def create(self) -> AsyncStreamingHttpClient: ...
