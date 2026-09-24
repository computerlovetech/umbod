from typing import Annotated, Any, Literal, Union

from pydantic import ConfigDict, Field, SecretStr, model_validator

from umbod.core.capabilities.descriptions import CapabilityDescription
from umbod.core.capabilities.tools.names import normalize_tool_name_prefix
from umbod.proxies import Model
from umbod.rest.connectors.schemas import (
    CapabilityDescriptionOverrideResponse,
    ConnectorPublicationResponse,
    ConnectorPublicationStatus,
    InitialCapabilityDescriptionOverride,
    SystemInitialCapabilityDescriptionOverride,
    ToolActivationBatchRequest,
    ToolActivationBatchRequestItem,
    ToolActivationBatchResponse,
    ToolActivationBatchResponseItem,
)

OpenApiAvailableAction = Literal["import", "publish", "unpublish"]
OpenApiPublicationStatus = ConnectorPublicationStatus
OpenApiToolActivationBatchRequest = ToolActivationBatchRequest
OpenApiToolActivationBatchRequestItem = ToolActivationBatchRequestItem
OpenApiToolActivationBatchResponse = ToolActivationBatchResponse
OpenApiToolActivationBatchResponseItem = ToolActivationBatchResponseItem
OpenApiPublicationResponse = ConnectorPublicationResponse


class CreateOpenApiConnectorRequest(Model):
    model_config = ConfigDict(extra="forbid")

    display_name: str
    tool_name_prefix: str = Field(pattern=r"^[a-zA-Z0-9_-]+$")
    capability_description: CapabilityDescription
    capability_description_override: InitialCapabilityDescriptionOverride = Field(
        default_factory=SystemInitialCapabilityDescriptionOverride
    )

    @model_validator(mode="before")
    @classmethod
    def default_missing_tool_name_prefix(cls, data: Any) -> Any:
        if not isinstance(data, dict) or "tool_name_prefix" in data:
            return data
        return {
            **data,
            "tool_name_prefix": normalize_tool_name_prefix(str(data.get("display_name", ""))),
        }


class ImportOpenApiCatalogRequest(Model):
    model_config = ConfigDict(extra="forbid")

    document: dict[str, object]
    approved_hosts: tuple[str, ...]


class OpenApiConnectorResponse(Model):
    model_config = ConfigDict(extra="forbid")

    connector_id: str
    display_name: str
    tool_name_prefix: str
    capability_description: CapabilityDescription
    base_capability_description: CapabilityDescription
    effective_capability_description: CapabilityDescription
    capability_description_override: CapabilityDescriptionOverrideResponse
    created_at: str
    updated_at: str
    publication_status: OpenApiPublicationStatus
    available_actions: tuple[OpenApiAvailableAction, ...]


class OpenApiConnectorSummaryResponse(Model):
    model_config = ConfigDict(extra="forbid")

    connector_id: str
    display_name: str
    publication_status: OpenApiPublicationStatus
    available_actions: tuple[OpenApiAvailableAction, ...]


class OpenApiConnectorListResponse(Model):
    connectors: tuple[OpenApiConnectorSummaryResponse, ...]


class OpenApiCatalogImportResponse(Model):
    model_config = ConfigDict(extra="forbid")

    connector_id: str
    catalog_id: str
    operation_ids: tuple[str, ...]
    approved_hosts: tuple[str, ...]
    selected_server_url: str
    imported_at: str


class OpenApiOperationToolResponseBase(Model):
    model_config = ConfigDict(extra="forbid")

    operation_id: str
    method: str
    path: str
    summary: str
    description: str
    activation_status: str
    parameters: dict[str, object]


class OpenApiOperationToolWithoutOutputSchemaResponse(OpenApiOperationToolResponseBase):
    output_schema_status: Literal["absent"] = "absent"


class OpenApiOperationToolWithOutputSchemaResponse(OpenApiOperationToolResponseBase):
    output_schema_status: Literal["present"] = "present"
    output_schema: dict[str, Any]


OpenApiOperationToolResponse = Annotated[
    Union[
        OpenApiOperationToolWithoutOutputSchemaResponse,
        OpenApiOperationToolWithOutputSchemaResponse,
    ],
    Field(discriminator="output_schema_status"),
]


class OpenApiOperationToolListResponse(Model):
    model_config = ConfigDict(extra="forbid")

    tools: list[OpenApiOperationToolResponse]


class OpenApiConfigurationRequest(Model):
    model_config = ConfigDict(extra="forbid")

    authentication_type: Literal["none", "bearer"] = "bearer"
    bearer_token: SecretStr = SecretStr("")


class OpenApiConfigurationResponse(Model):
    model_config = ConfigDict(extra="forbid")

    configured: bool
    authentication_type: Literal["none", "bearer"]
    masked_token: Literal["********"] | None
