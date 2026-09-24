from typing import Optional

from umbod.core.capabilities import (
    AbsentCapabilityOutputSchema,
    CapabilityAvailability,
    CapabilityIdentity,
    CapabilityNotFoundError,
    NormalizedCapability,
    PresentCapabilityOutputSchema,
)
from umbod.core.capabilities.descriptions import (
    ConnectorCapabilityDescriptionKey,
    ConnectorCapabilityDescriptionOverrideStore,
    OverriddenCapabilityDescription,
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
from umbod.core.permissions.domain import ConnectorToolRef
from umbod.core.permissions.ports import GroupPermissionReader


class StoreBackedOpenApiCapabilityCatalog:
    def __init__(self, store: OpenApiConnectorStore) -> None:
        self._store = store

    async def list_capabilities(self) -> tuple[NormalizedCapability, ...]:
        capabilities: list[NormalizedCapability] = []
        for connector in await self._store.list_connectors():
            for summary in await self._store.list_operation_summaries(connector.connector_id):
                operation = await self._store.read_operation(connector.connector_id, summary.operation_id)
                if operation is not None:
                    capabilities.append(
                        _normalize_authorized_operation(
                            operation, connector, connector.capability_description
                        )
                    )
        return tuple(capabilities)

    async def resolve(self, identity: CapabilityIdentity) -> NormalizedCapability:
        if identity.connector_kind != "openapi":
            raise CapabilityNotFoundError(identity)
        operation = await self._store.read_operation(
            identity.connector_id, identity.capability_key
        )
        if operation is None:
            raise CapabilityNotFoundError(identity)
        connector = await self._connector(identity)
        return _normalize_authorized_operation(
            operation, connector, connector.capability_description
        )

    async def _connector(self, identity: CapabilityIdentity) -> OpenApiConnector:
        try:
            return await self._store.get_connector(identity.connector_id)
        except KeyError as error:
            raise CapabilityNotFoundError(identity) from error


class PersistedAuthorizedOpenApiCapabilityCatalog:
    def __init__(
        self,
        store: OpenApiConnectorStore,
        permissions: GroupPermissionReader,
        groups: tuple[str, ...],
        availability: Optional[CapabilityAvailability],
        description_overrides: ConnectorCapabilityDescriptionOverrideStore,
    ) -> None:
        self._store = store
        self._permissions = permissions
        self._groups = groups
        self._availability = availability
        self._description_overrides = description_overrides

    async def list_capabilities(self) -> tuple[NormalizedCapability, ...]:
        grants = await self._grants()
        capabilities: list[NormalizedCapability] = []
        for connector in await self._store.list_connectors():
            operations = await self._available_operations(connector.connector_id)
            description = await self._connector_description(connector)
            capabilities.extend(
                _normalize_authorized_operation(operation, connector, description)
                for operation in operations
                if grants.allows(connector.connector_id, operation.summary.operation_id)
            )
        return tuple(capabilities)

    async def resolve(self, identity: CapabilityIdentity) -> NormalizedCapability:
        if identity.connector_kind != "openapi":
            raise CapabilityNotFoundError(identity)
        capabilities = await self.list_capabilities()
        for capability in capabilities:
            if capability.identity == identity:
                return capability
        raise CapabilityNotFoundError(identity)

    async def _available_operations(
        self, connector_id: str
    ) -> tuple[PersistedOpenApiOperation, ...]:
        if self._availability is not None:
            summaries = await self._store.list_operation_summaries(connector_id)
            operations: list[PersistedOpenApiOperation] = []
            for summary in summaries:
                identity = CapabilityIdentity(
                    connector_kind="openapi",
                    connector_id=connector_id,
                    capability_kind="tool",
            capability_key=summary.operation_id,
                )
                if not await self._availability.is_available(identity):
                    continue
                operation = await self._store.read_operation(connector_id, summary.operation_id)
                if operation is not None:
                    operations.append(operation)
            return tuple(operations)
        summaries = await self._store.list_operation_summaries(connector_id)
        persisted = [
            await self._store.read_operation(connector_id, summary.operation_id)
            for summary in summaries
        ]
        return tuple(operation for operation in persisted if operation is not None)

    async def _connector_description(self, connector: OpenApiConnector) -> str:
        states = await self._description_overrides.get_many(
            (ConnectorCapabilityDescriptionKey(kind="openapi", connector_id=connector.connector_id),)
        )
        state = states[0]
        if isinstance(state, OverriddenCapabilityDescription):
            return state.description
        return connector.capability_description

    async def _grants(self) -> "_OpenApiGrants":
        connectors: set[str] = set()
        operations: set[ConnectorToolRef] = set()
        for group in dict.fromkeys(self._groups):
            permissions = await self._permissions.list_group_permissions(group)
            connectors.update(permissions.connector_ids)
            operations.update(permissions.tools)
        return _OpenApiGrants(frozenset(connectors), frozenset(operations))


class _OpenApiGrants:
    def __init__(
        self, connectors: frozenset[str], operations: frozenset[ConnectorToolRef]
    ) -> None:
        self._connectors = connectors
        self._operations = operations

    def allows(self, connector_id: str, operation_id: str) -> bool:
        return connector_id in self._connectors or ConnectorToolRef(
            connector_id, operation_id
        ) in self._operations


def _normalize_authorized_operation(
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
