from typing import Protocol

from umbod.core.connectors.openapi.execution import AsyncStreamingHttpClient
from umbod.core.connectors.openapi.stores import OpenApiConnectorStore
from umbod.core.permissions.ports import GroupPermissionReader


class CurrentPrincipal(Protocol):
    def subject(self) -> str: ...

    def groups(self) -> tuple[str, ...]: ...


CurrentPrincipalGroups = CurrentPrincipal


class OpenApiConnectorStoreFactory(Protocol):
    async def create(self) -> OpenApiConnectorStore: ...


class GroupPermissionReaderFactory(Protocol):
    async def create(self) -> GroupPermissionReader: ...


class OutboundHttpClientFactoryPort(Protocol):
    def create(self) -> AsyncStreamingHttpClient: ...
