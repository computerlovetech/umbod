from typing import Protocol

from umbod.core.invocation.tools.execution import ToolExecutionPipeline
from umbod.core.connectors.openapi.execution import (
    AsyncStreamingHttpClient,
    OpenApiCapabilityExecutionResult,
    OpenApiExecutionResponse,
    OpenApiOperationInput,
)
from umbod.core.connectors.openapi.stores import OpenApiConnectorStore
from umbod.core.permissions.ports import GroupPermissionReader


class OpenApiExecutionService(Protocol):
    async def execute(
        self, operation_input: OpenApiOperationInput, groups: tuple[str, ...]
    ) -> OpenApiCapabilityExecutionResult: ...


class OpenApiExecutionServiceFactory(Protocol):
    async def create(
        self,
        store: OpenApiConnectorStore,
        permission_reader: GroupPermissionReader,
        client: AsyncStreamingHttpClient,
        execution_pipeline: ToolExecutionPipeline[OpenApiExecutionResponse],
    ) -> OpenApiExecutionService: ...


class OpenApiConnectorStoreFactory(Protocol):
    async def create(self) -> OpenApiConnectorStore: ...


class GroupPermissionReaderFactory(Protocol):
    async def create(self) -> GroupPermissionReader: ...


class OutboundHttpClientFactoryPort(Protocol):
    def create(self) -> AsyncStreamingHttpClient: ...
