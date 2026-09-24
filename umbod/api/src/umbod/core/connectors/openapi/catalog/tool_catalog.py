from umbod.core.activation import ActivationStore, CapabilityRef
from umbod.core.capabilities.tools.output_schema import ConnectorToolOutputSchema
from umbod.core.connectors.openapi.catalog.capability_schemas import (
    openapi_output_schema,
    openapi_parameters_schema,
)
from umbod.core.connectors.openapi.stores.catalog_models import OpenApiOperationSummary
from umbod.core.connectors.openapi.stores import (
    CurrentOpenApiCatalogHeaderReader,
    OpenApiOperationReader,
    OpenApiOperationSummaryReader,
)
from umbod.proxies import Model
from pydantic import ConfigDict


class OpenApiOperationTool(Model):
    model_config = ConfigDict(extra="forbid", frozen=True)

    operation_id: str
    method: str
    path: str
    summary: str
    description: str
    activation_status: str
    parameters: dict[str, object]
    output_schema: ConnectorToolOutputSchema


class OpenApiConnectorToolCatalog:
    def __init__(
        self,
        store: CurrentOpenApiCatalogHeaderReader
        | OpenApiOperationReader
        | OpenApiOperationSummaryReader,
        activation_store: ActivationStore,
    ) -> None:
        self._store = store
        self._activation_store = activation_store

    async def list_operation_tools(self, connector_id: str) -> tuple[OpenApiOperationTool, ...]:
        tools: list[OpenApiOperationTool] = []
        for endpoint in await self._summaries(connector_id):
            operation = await self._store.read_operation(connector_id, endpoint.operation_id)
            if operation is None:
                continue
            status = await self._activation_store.get_status(
                CapabilityRef(
                    connector_kind="openapi",
                    connector_id=connector_id,
                    capability_kind="tool",
                    capability_key=endpoint.operation_id,
                )
            )
            tools.append(
                OpenApiOperationTool(
                    operation_id=endpoint.operation_id,
                    method=endpoint.method.upper(),
                    path=endpoint.path,
                    summary=endpoint.summary,
                    description=endpoint.description,
                    activation_status=status.value,
                    parameters=openapi_parameters_schema(operation.capability),
                    output_schema=openapi_output_schema(operation.capability),
                )
            )
        return tuple(tools)

    async def _summaries(self, connector_id: str) -> tuple[OpenApiOperationSummary, ...]:
        return await self._store.list_operation_summaries(connector_id)
