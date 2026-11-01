from umbod.core.capabilities import (
    AbsentCapabilityOutputSchema,
    CapabilityIdentity,
    CapabilityNotFoundError,
    NormalizedCapability,
    PresentCapabilityOutputSchema,
)
from umbod.core.capabilities.tools.output_schema import PresentConnectorToolOutputSchema
from umbod.core.connectors.openapi.catalog.capability_schemas import (
    openapi_execution_schema,
    openapi_output_schema,
)
from umbod.core.connectors.openapi.stores.catalog_models import PersistedOpenApiOperation
from umbod.core.connectors.openapi.management.models import OpenApiConnector
from umbod.core.connectors.openapi.models import OpenApiEndpointCapability
from umbod.core.connectors.openapi.stores import OpenApiConnectorStore


class StoreBackedOpenApiCapabilityCatalog:
    def __init__(self, store: OpenApiConnectorStore) -> None:
        self._store = store

    async def list_capabilities(self) -> tuple[NormalizedCapability, ...]:
        capabilities: list[NormalizedCapability] = []
        for connector in await self._store.list_connectors():
            capabilities.extend(await self.list_connector_capabilities(connector))
        return tuple(capabilities)

    async def list_connector_capabilities(
        self, connector: OpenApiConnector
    ) -> tuple[NormalizedCapability, ...]:
        operations = await self._store.list_operations(connector.connector_id)
        return tuple(
            _normalize_operation(
                operation, connector, connector.capability_description
            )
            for operation in operations
        )

    async def resolve(self, identity: CapabilityIdentity) -> NormalizedCapability:
        if identity.connector_kind != "openapi":
            raise CapabilityNotFoundError(identity)
        operation = await self._store.read_operation(
            identity.connector_id, identity.capability_key
        )
        if operation is None:
            raise CapabilityNotFoundError(identity)
        connector = await self._connector(identity)
        return _normalize_operation(
            operation, connector, connector.capability_description
        )

    async def _connector(self, identity: CapabilityIdentity) -> OpenApiConnector:
        try:
            return await self._store.get_connector(identity.connector_id)
        except KeyError as error:
            raise CapabilityNotFoundError(identity) from error


def _normalize_operation(
    operation: PersistedOpenApiOperation,
    connector: OpenApiConnector,
    connector_description: str,
) -> NormalizedCapability:
    schema = openapi_execution_schema(connector.connector_id, operation.capability)
    capability = _normalized_operation(operation, schema)
    return capability.model_copy(
        update={
            "connector_display_name": connector.display_name,
            "connector_capability_description": connector_description,
            "search_hints": _search_hints(operation),
        }
    )


def _normalized_operation(
    operation: PersistedOpenApiOperation, input_schema: dict[str, object]
) -> NormalizedCapability:
    operation_id = operation.summary.operation_id
    endpoint = operation.capability
    return NormalizedCapability(
        identity=CapabilityIdentity(
            connector_kind="openapi",
            connector_id=operation.summary.connector_id,
            capability_kind="tool",
            capability_key=operation_id,
        ),
        title=operation.summary.summary.strip() or operation_id,
        description=endpoint.description.strip() or endpoint.summary.strip() or operation_id,
        input_schema=input_schema,
        output_schema=_normalized_output_schema(operation),
    )


def _normalized_output_schema(
    operation: PersistedOpenApiOperation,
) -> AbsentCapabilityOutputSchema | PresentCapabilityOutputSchema:
    output_schema = openapi_output_schema(operation.capability)
    if isinstance(output_schema, PresentConnectorToolOutputSchema):
        return PresentCapabilityOutputSchema(schema=output_schema.output_schema)
    return AbsentCapabilityOutputSchema()


def _search_hints(operation: PersistedOpenApiOperation) -> tuple[str, ...]:
    endpoint = operation.capability
    values = (
        endpoint.summary,
        *operation.summary.tags,
        *(parameter.name for parameter in endpoint.parameters),
        *_schema_property_names(endpoint),
    )
    return tuple(value for value in values if value.strip())


def _schema_property_names(endpoint: OpenApiEndpointCapability) -> tuple[str, ...]:
    schemas = tuple(parameter.capability_schema for parameter in endpoint.parameters) + tuple(
        body.capability_schema for body in endpoint.request_bodies
    )
    names: list[str] = []
    for schema in schemas:
        names.extend(_nested_property_names(schema))
    return tuple(names)


def _nested_property_names(schema: object) -> tuple[str, ...]:
    properties = getattr(schema, "properties", None)
    if isinstance(properties, dict):
        names = list(properties)
        for child in properties.values():
            names.extend(_nested_property_names(child))
        return tuple(names)
    items = getattr(schema, "items", None)
    return _nested_property_names(items) if items is not None else ()
