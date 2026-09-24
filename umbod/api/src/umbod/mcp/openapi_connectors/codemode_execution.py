import inspect
import logging

from fastmcp import FastMCP
from pydantic import JsonValue, TypeAdapter

from umbod.core.capabilities import AvailabilityAwareCapabilityAuthorizer
from umbod.core.invocation.tools.execution import ToolExecutionPipeline, create_tool_execution_pipeline
from umbod.core.connectors.openapi.execution import (
    AggregateOpenApiOperationResolver,
    AsyncStreamingHttpClient,
    BearerOpenApiRequestAuthenticator,
    ExactGroupOpenApiCapabilityAuthorizer,
    ExactHttpsDestinationPolicy,
    HttpxOutboundOperationAdapter,
    IdentityOpenApiResponseNormalizer,
    MissingJsonBody,
    OpenApiCapabilityExecutionService,
    OpenApiExecutionLimits,
    OpenApiExecutionResponse,
    OpenApiOperationInput,
    PresentJsonBody,
    StrictOpenApiRequestCompiler,
)
from umbod.core.connectors.openapi.stores import OpenApiConnectorStore
from umbod.core.permissions.ports import GroupPermissionReader
from umbod.mcp.connectors.tools import ConnectorTelemetryInterceptor
from umbod.mcp.connectors.tools.deployment_modes.codemode import (
    OpenApiCodeModeExecutor,
    OpenApiCodeModeInvocation,
)
from umbod.mcp.logging import ConnectorToolInvocationLogger
from umbod.mcp.openapi_connectors.availability import openapi_availability_reader
from umbod.mcp.openapi_connectors.configuration import openapi_configuration_adapter
from umbod.mcp.openapi_connectors.principal import JwtCurrentPrincipalGroups

logger = logging.getLogger(__name__)


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
    def __init__(self, server: FastMCP, tool_invocation_logger: ConnectorToolInvocationLogger) -> None:
        self._server = server
        self._tool_invocation_logger = tool_invocation_logger

    async def execute(self, invocation: OpenApiCodeModeInvocation) -> JsonValue:
        store = await self._server.openapi_connector_store_factory.create()
        permission_reader = await self._server.group_permission_reader_factory.create()
        client = self._server.openapi_outbound_http_client_factory.create()
        try:
            connector_name = await self._connector_display_name(store, invocation)
            execution_pipeline = create_tool_execution_pipeline(
                self._server.connector_invocation_policy,
                (
                    ConnectorTelemetryInterceptor(
                        connector_name=connector_name,
                        tool_invocation_logger=self._tool_invocation_logger,
                        metrics_recorder=self._server.metrics_recorder,
                        result_is_error=lambda result: False,
                    ),
                ),
            )
            service = await self._execution_service(store, permission_reader, client, execution_pipeline)
            operation_input = self._operation_input(invocation)
            principal = JwtCurrentPrincipalGroups(self._server.permission_group_claim)
            result = await service.execute(operation_input, principal.groups())
            return result.model_dump(mode='json')
        finally:
            await _close_resource(client)
            await _close_resource(permission_reader)
            await _close_resource(store)

    async def _execution_service(
        self,
        store: OpenApiConnectorStore,
        permission_reader: GroupPermissionReader,
        client: AsyncStreamingHttpClient,
        execution_pipeline: ToolExecutionPipeline[OpenApiExecutionResponse],
    ) -> OpenApiCapabilityExecutionService:
        availability = openapi_availability_reader(self._server, store)
        permission_authorizer = ExactGroupOpenApiCapabilityAuthorizer(permission_reader)
        authorizer = (
            AvailabilityAwareCapabilityAuthorizer(permission_authorizer, availability, 'openapi')
            if availability is not None
            else permission_authorizer
        )
        return OpenApiCapabilityExecutionService(
            active_catalog_reader=store,
            authorizer=authorizer,
            resolver=AggregateOpenApiOperationResolver(),
            compiler=StrictOpenApiRequestCompiler(ExactHttpsDestinationPolicy()),
            transport=HttpxOutboundOperationAdapter(client),
            normalizer=IdentityOpenApiResponseNormalizer(),
            limits=OpenApiExecutionLimits(
                timeout_seconds=self._server.openapi_execution_timeout_seconds,
                maximum_response_bytes=self._server.openapi_execution_maximum_response_bytes,
            ),
            authenticator=BearerOpenApiRequestAuthenticator(await openapi_configuration_adapter(self._server)),
            execution_pipeline=execution_pipeline,
        )

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
    def create(self, server: FastMCP, tool_invocation_logger: ConnectorToolInvocationLogger) -> OpenApiCodeModeExecutor:
        return OpenApiCodeModeExecutionAdapter(server, tool_invocation_logger).execute


def build_openapi_codemode_executor(
    server: FastMCP,
    tool_invocation_logger: ConnectorToolInvocationLogger,
) -> OpenApiCodeModeExecutor:
    return OpenApiCodeModeExecutionAdapterFactory().create(server, tool_invocation_logger)
