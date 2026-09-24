from typing import Protocol

from umbod.core.capabilities.descriptions import (
    ConnectorCapabilityDescriptionOverrideStore,
)
from umbod.core.configuration import ConnectorCurrentConfigurationStore
from umbod.core.connectors.native.models import ConnectorMetadata
from umbod.core.connectors.native.registry import ConnectorDefinition
from umbod.core.connectors.native.tools.descriptions import (
    ConnectorToolDescriptionWithOutputSchema,
)
from umbod.core.connectors.native.tools.parameter_schema import ToolParameterObjectSchema
from umbod.core.publishing import ConnectorPublishingStore
from umbod.rest.connectors.capability_description import capability_description_fields
from umbod.rest.connectors.native.schemas import (
    ConnectorDetailResponse,
    ConnectorListItemResponse,
    ConnectorToolDetailWithOutputSchemaResponse,
    ConnectorToolDetailWithoutOutputSchemaResponse,
)
from umbod.rest.connectors.publication import native_available_actions, resolve_publication_status


class ConnectorPresentationService(Protocol):
    async def list_item(self, connector: ConnectorMetadata) -> ConnectorListItemResponse: ...

    async def detail(
        self, connector_definition: ConnectorDefinition
    ) -> ConnectorDetailResponse: ...


class StoreBackedConnectorPresentationService:
    def __init__(
        self,
        configuration_store: ConnectorCurrentConfigurationStore,
        publishing_store: ConnectorPublishingStore,
        override_store: ConnectorCapabilityDescriptionOverrideStore,
    ) -> None:
        self._configuration_store = configuration_store
        self._publishing_store = publishing_store
        self._override_store = override_store

    async def list_item(self, connector: ConnectorMetadata) -> ConnectorListItemResponse:
        status = await resolve_publication_status(
            connector_id=connector.id,
            publishing_store=self._publishing_store,
            is_configured=await self._configuration_store.get_current_configuration(connector.id)
            is not None,
        )
        return ConnectorListItemResponse(
            id=connector.id,
            display_name=connector.display_name,
            description=connector.description,
            icon_data_url=connector.icon_data_url,
            extension={"source": connector.extension.source},
            publication_status=status,
            available_actions=native_available_actions(status),
        )

    async def detail(self, connector_definition: ConnectorDefinition) -> ConnectorDetailResponse:
        connector = connector_definition.metadata
        return ConnectorDetailResponse(
            **connector.model_dump(exclude={"capability_description"}),
            **await capability_description_fields(
                connector_kind="native",
                connector_id=connector.id,
                base_description=connector.capability_description,
                override_store=self._override_store,
            ),
            publication_status=await resolve_publication_status(
                connector_id=connector.id,
                publishing_store=self._publishing_store,
                is_configured=await self._configuration_store.get_current_configuration(
                    connector.id
                )
                is not None,
            ),
            tools=[
                (
                    ConnectorToolDetailWithOutputSchemaResponse(
                        operation_name=tool.operation_name,
                        label=tool.label,
                        description=tool.description,
                        parameters=ToolParameterObjectSchema.from_descriptions(tool.parameters),
                        output_schema=tool.output_schema,
                    )
                    if isinstance(tool, ConnectorToolDescriptionWithOutputSchema)
                    else ConnectorToolDetailWithoutOutputSchemaResponse(
                        operation_name=tool.operation_name,
                        label=tool.label,
                        description=tool.description,
                        parameters=ToolParameterObjectSchema.from_descriptions(tool.parameters),
                    )
                )
                for tool in connector_definition.tool_descriptions.values()
            ],
        )
