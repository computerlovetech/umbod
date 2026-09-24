from datetime import datetime
from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic.types import JsonValue

from umbod.core.capabilities.descriptions import CapabilityDescription
from umbod.core.connectors.downstream_mcp.models import (
    EndpointUrl,
    PublicPath,
    StaticTokenHeaderType,
    ToolNamePrefix,
    default_tool_name_prefix,
    validate_custom_header_name,
)
from umbod.rest.connectors.schemas import (
    ConnectorPublicationResponse,
    InitialCapabilityDescriptionOverride,
    PromptActivationBatchRequest as PromptActivationBatchRequest,
    PromptActivationBatchRequestItem as PromptActivationBatchRequestItem,
    PromptActivationBatchResponse as PromptActivationBatchResponse,
    PromptActivationBatchResponseItem as PromptActivationBatchResponseItem,
    ResourceActivationBatchRequest as ResourceActivationBatchRequest,
    ResourceActivationBatchRequestItem as ResourceActivationBatchRequestItem,
    ResourceActivationBatchResponse as ResourceActivationBatchResponse,
    ResourceActivationBatchResponseItem as ResourceActivationBatchResponseItem,
    SystemInitialCapabilityDescriptionOverride,
    ToolActivationBatchRequest as ToolActivationBatchRequest,
    ToolActivationBatchRequestItem as ToolActivationBatchRequestItem,
    ToolActivationBatchResponse as ToolActivationBatchResponse,
    ToolActivationBatchResponseItem as ToolActivationBatchResponseItem,
)


class ApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CreateConnectorMetadataRequest(ApiModel):
    display_name: str = Field(min_length=1)
    tool_name_prefix: ToolNamePrefix
    capability_description: CapabilityDescription
    public_path: PublicPath

    @model_validator(mode="before")
    @classmethod
    def default_missing_tool_name_prefix(cls, value: object) -> object:
        if not isinstance(value, dict) or "tool_name_prefix" in value:
            return value
        return {
            **value,
            "tool_name_prefix": default_tool_name_prefix(str(value.get("display_name", ""))),
        }


class NoAuthCreateConfigurationRequest(ApiModel):
    auth_mode: Literal["none"]
    endpoint_url: EndpointUrl
    header_type: None = None
    custom_header_name: None = None
    bearer_token: None = None


class BearerCreateConfigurationRequest(ApiModel):
    auth_mode: Literal["static_bearer"]
    endpoint_url: EndpointUrl
    header_type: StaticTokenHeaderType = "bearer"
    custom_header_name: str | None = None
    bearer_token: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_header_configuration(self) -> "BearerCreateConfigurationRequest":
        if self.header_type == "custom":
            if self.custom_header_name is None:
                raise ValueError("custom header name is required")
            validate_custom_header_name(self.custom_header_name)
        elif self.custom_header_name is not None:
            raise ValueError("custom header name is forbidden")
        return self


CreateConnectorConfigurationRequest = Annotated[
    Union[
        NoAuthCreateConfigurationRequest,
        BearerCreateConfigurationRequest,
    ],
    Field(discriminator="auth_mode"),
]


class CreateConnectorRequest(ApiModel):
    metadata: CreateConnectorMetadataRequest
    configuration: CreateConnectorConfigurationRequest
    capability_description_override: InitialCapabilityDescriptionOverride = Field(
        default_factory=SystemInitialCapabilityDescriptionOverride
    )


class ConnectorMetadataPatchRequest(ApiModel):
    display_name: str | None = Field(default=None, min_length=1)
    tool_name_prefix: ToolNamePrefix | None = None
    capability_description: CapabilityDescription | None = None
    public_path: PublicPath | None = None

    @model_validator(mode="before")
    @classmethod
    def reject_explicit_null_fields(cls, value: object) -> object:
        if isinstance(value, dict) and any(field_value is None for field_value in value.values()):
            raise ValueError("metadata fields cannot be null")
        return value

    @model_validator(mode="after")
    def at_least_one_field_is_present(self) -> "ConnectorMetadataPatchRequest":
        if not self.model_fields_set:
            raise ValueError("at least one metadata field is required")
        return self


class NoAuthConfigurationRequest(ApiModel):
    auth_mode: Literal["none"]
    endpoint_url: EndpointUrl
    header_type: None = None
    custom_header_name: None = None
    bearer_token: None = None


class BearerConfigurationRequest(ApiModel):
    auth_mode: Literal["static_bearer"]
    endpoint_url: EndpointUrl
    header_type: StaticTokenHeaderType = "bearer"
    custom_header_name: str | None = None
    bearer_token: str | None = None

    @model_validator(mode="after")
    def validate_header_configuration(self) -> "BearerConfigurationRequest":
        if self.header_type == "custom":
            if self.custom_header_name is None:
                raise ValueError("custom header name is required")
            validate_custom_header_name(self.custom_header_name)
        elif self.custom_header_name is not None:
            raise ValueError("custom header name is forbidden")
        return self


ConnectorConfigurationRequest = Annotated[
    Union[NoAuthConfigurationRequest, BearerConfigurationRequest],
    Field(discriminator="auth_mode"),
]


class ConnectorConfigurationResponse(ApiModel):
    endpoint_url: str
    auth_mode: Literal["none", "static_bearer", "oauth"]
    header_type: StaticTokenHeaderType
    custom_header_name: str | None
    credential_configured: bool


class ConnectorHealthResponse(ApiModel):
    status: Literal["unknown", "healthy", "unhealthy"]
    checked_at: datetime | None = None
    reason: str | None = None


class SystemCapabilityDescriptionOverrideResponse(ApiModel):
    state: Literal["system"] = "system"
    revision: Annotated[int, Field(ge=0)]


class OverriddenCapabilityDescriptionOverrideResponse(ApiModel):
    state: Literal["overridden"] = "overridden"
    description: CapabilityDescription
    revision: Annotated[int, Field(ge=1)]


CapabilityDescriptionOverrideResponse = Annotated[
    Union[
        SystemCapabilityDescriptionOverrideResponse,
        OverriddenCapabilityDescriptionOverrideResponse,
    ],
    Field(discriminator="state"),
]


class ConnectorResponse(ApiModel):
    connector_id: str
    display_name: str
    tool_name_prefix: str
    icon_url: str = ""
    capability_description: CapabilityDescription
    base_capability_description: CapabilityDescription
    effective_capability_description: CapabilityDescription
    capability_description_override: CapabilityDescriptionOverrideResponse
    endpoint_url: str
    public_path: str
    public_url: str
    auth_mode: Literal["none", "static_bearer", "oauth"]
    header_type: StaticTokenHeaderType
    custom_header_name: str | None
    credential_configured: bool
    publication_status: Literal["published", "unpublished"]
    health: ConnectorHealthResponse


class ConnectorSummaryResponse(ApiModel):
    connector_id: str
    display_name: str
    icon_url: str = ""
    auth_mode: Literal["none", "static_bearer", "oauth"] = "none"
    publication_status: Literal["published", "unpublished"]
    health: ConnectorHealthResponse


class ConnectorListResponse(ApiModel):
    connectors: tuple[ConnectorSummaryResponse, ...]


class ToolResponse(ApiModel):
    name: str
    title: str
    description: str
    input_schema: dict[str, JsonValue]
    output_schema: dict[str, JsonValue] | None = None
    activation_status: Literal["enabled", "disabled"]


class ToolListResponse(ApiModel):
    discovered_at: datetime | None = None
    tools: tuple[ToolResponse, ...]


class PromptArgumentResponse(ApiModel):
    name: str
    description: str
    required: bool


class PromptResponse(ApiModel):
    name: str
    description: str
    arguments: tuple[PromptArgumentResponse, ...]
    activation_status: Literal["enabled", "disabled"] = "disabled"


class PromptCatalogResponse(ApiModel):
    prompts: tuple[PromptResponse, ...]
    available_actions: tuple[Literal["invoke_prompt", "activate", "edit"], ...]


class ResourceResponse(ApiModel):
    kind: Literal["resource", "resource_template"]
    name: str
    description: str
    uri: str
    activation_status: Literal["enabled", "disabled"] = "disabled"


class ResourceCatalogResponse(ApiModel):
    resources: tuple[ResourceResponse, ...]
    available_actions: tuple[Literal["read_resource", "activate", "edit"], ...]


PublicationResponse = ConnectorPublicationResponse
