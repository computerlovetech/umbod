import inspect
import logging

from fastmcp import FastMCP
from pydantic import JsonValue, TypeAdapter

from umbod.core.connectors.openapi.execution import (
    MissingJsonBody,
    OpenApiExecutionResponse,
    OpenApiOperationInput,
    PresentJsonBody,
)
from umbod.core.connectors.openapi.stores import OpenApiConnectorStore
from umbod.mcp.signals import McpToolExecutionPipelineFactory
from umbod.mcp.connectors.native.tools.deployment_modes.codemode import (
    OpenApiCodeModeExecutor,
    OpenApiCodeModeInvocation,
)
from umbod.mcp.connectors.openapi.execution_service_factory import OpenApiCapabilityExecutionServiceFactory
from umbod.mcp.connectors.openapi.ports import OpenApiExecutionServiceFactory
from umbod.mcp.connectors.openapi.deps import capture_openapi_groups

logger = logging.getLogger(__name__)


def openapi_response_is_error(result: object) -> bool:
    return isinstance(result, OpenApiExecutionResponse) and result.status >= 400


async def _close_resource(resource: object) -> None:
    close = getattr(resource, 'aclose', None)
    if not callable(close):
        close = getattr(resource, 'close', None)
    if not callable(close):
        return
    result = close()
    if inspect.isawaitable(result):
        await result


class OpenApiCodeModeExecutionAdapter:
    def __init__(
        self,
        server: FastMCP,
        execution_pipelines: McpToolExecutionPipelineFactory,
        execution_services: OpenApiExecutionServiceFactory,
    ) -> None:
        self._server = server
        self._execution_pipelines = execution_pipelines
        self._execution_services = execution_services

    async def execute(self, invocation: OpenApiCodeModeInvocation) -> JsonValue:
        groups = capture_openapi_groups(self._server)
        store = await self._server.openapi_connector_store_factory.create()
        permission_reader = await self._server.group_permission_reader_factory.create()
        client = self._server.openapi_outbound_http_client_factory.create()
        try:
            connector_name = await self._connector_display_name(store, invocation)
            execution_pipeline = self._execution_pipelines.create(connector_name, openapi_response_is_error)
            service = await self._execution_services.create(store, permission_reader, client, execution_pipeline)
            operation_input = self._operation_input(invocation)
            result = await service.execute(operation_input, groups.group_ids)
            return result.model_dump(mode='json')
        finally:
            await _close_resource(client)
            await _close_resource(permission_reader)
            await _close_resource(store)

    @staticmethod
    def _operation_input(invocation: OpenApiCodeModeInvocation) -> OpenApiOperationInput:
        body = TypeAdapter(MissingJsonBody | PresentJsonBody).validate_python(invocation.body)
        return OpenApiOperationInput(
            connector_id=invocation.connector_id,
            operation_id=invocation.operation_id,
            path=invocation.path,
            query=invocation.query,
            headers=invocation.headers,
            body=body,
        )

    @staticmethod
    async def _connector_display_name(store: OpenApiConnectorStore, invocation: OpenApiCodeModeInvocation) -> str:
        connector_name = invocation.connector_id
        try:
            connector_name = (await store.get_connector(invocation.connector_id)).display_name
        except Exception:
            logger.exception(
                'OpenAPI connector display name lookup failed',
                extra={'connector_id': invocation.connector_id, 'operation_name': invocation.operation_id},
            )
        return connector_name


class OpenApiCodeModeExecutionAdapterFactory:
    def create(
        self,
        server: FastMCP,
        execution_pipelines: McpToolExecutionPipelineFactory,
        execution_services: OpenApiExecutionServiceFactory,
    ) -> OpenApiCodeModeExecutor:
        return OpenApiCodeModeExecutionAdapter(server, execution_pipelines, execution_services).execute


def build_openapi_codemode_executor(
    server: FastMCP,
    execution_pipelines: McpToolExecutionPipelineFactory,
) -> OpenApiCodeModeExecutor:
    return OpenApiCodeModeExecutionAdapterFactory().create(
        server, execution_pipelines, OpenApiCapabilityExecutionServiceFactory(server)
    )
