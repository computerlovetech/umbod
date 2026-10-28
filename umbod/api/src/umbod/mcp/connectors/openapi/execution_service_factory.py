from fastmcp import FastMCP

from umbod.core.capabilities import AvailabilityAwareCapabilityAuthorizer
from umbod.core.invocation.tools.execution import ToolExecutionPipeline
from umbod.core.connectors.openapi.execution import (
    AggregateOpenApiOperationResolver,
    AsyncStreamingHttpClient,
    BearerOpenApiRequestAuthenticator,
    ExactGroupOpenApiCapabilityAuthorizer,
    ExactHttpsDestinationPolicy,
    HttpxOutboundOperationAdapter,
    IdentityOpenApiResponseNormalizer,
    OpenApiCapabilityExecutionService,
    OpenApiExecutionLimits,
    OpenApiExecutionResponse,
    StrictOpenApiRequestCompiler,
)
from umbod.core.connectors.openapi.stores import OpenApiConnectorStore
from umbod.core.permissions.ports import GroupPermissionReader
from umbod.mcp.connectors.openapi.availability import openapi_availability_reader
from umbod.mcp.connectors.openapi.configuration import openapi_configuration_adapter


class OpenApiCapabilityExecutionServiceFactory:
    def __init__(self, server: FastMCP) -> None:
        self._server = server

    async def create(
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
