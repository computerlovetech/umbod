from typing import Annotated, Any, Literal, TypeAlias

from pydantic import ConfigDict, Field

from umbod.core.configuration.models import ConnectorConfigurationField
from umbod.core.connectors.native.models import (
    ConnectorMetadata,
    NonEmptyString,
)
from umbod.core.connectors.native.tools.parameter_schema import ToolParameterObjectSchema
from umbod.proxies import Model
from umbod.rest.connectors.schemas import (
    CapabilityDescriptionOverrideResponse,
    ConnectorPublicationResponse,
    ConnectorPublicationStatus,
    ConnectorToolInvocationPolicyConflictResponse as ConnectorToolInvocationPolicyConflictResponse,
    PromptActivationBatchRequest,
    PromptActivationBatchResponse,
    PromptActivationBatchResponseItem,
    ResourceActivationBatchRequest,
    ResourceActivationBatchResponse,
    ResourceActivationBatchResponseItem,
    ToolActivationBatchRequest,
    ToolActivationBatchRequestItem,
    ToolActivationBatchResponse,
    ToolActivationBatchResponseItem,
)

ConnectorToolActivationBatchRequest = ToolActivationBatchRequest
ConnectorToolActivationBatchRequestItem = ToolActivationBatchRequestItem
ConnectorToolActivationItemResponse = ToolActivationBatchResponseItem
ConnectorToolActivationListResponse = ToolActivationBatchResponse
ConnectorToolActivationBatchResponse = ToolActivationBatchResponse
ConnectorPromptActivationBatchRequest = PromptActivationBatchRequest
ConnectorPromptActivationBatchResponse = PromptActivationBatchResponse
ConnectorPromptActivationBatchResponseItem = PromptActivationBatchResponseItem
ConnectorResourceActivationBatchRequest = ResourceActivationBatchRequest
ConnectorResourceActivationBatchResponse = ResourceActivationBatchResponse
ConnectorResourceActivationBatchResponseItem = ResourceActivationBatchResponseItem


class ConnectorToolDetailResponseBase(Model):
    operation_name: NonEmptyString
    label: NonEmptyString
    description: NonEmptyString
    parameters: ToolParameterObjectSchema


class ConnectorToolDetailWithoutOutputSchemaResponse(ConnectorToolDetailResponseBase):
    output_schema_status: Literal["absent"] = "absent"


class ConnectorToolDetailWithOutputSchemaResponse(ConnectorToolDetailResponseBase):
    output_schema_status: Literal["present"] = "present"
    output_schema: dict[str, Any]


ConnectorToolDetailResponse: TypeAlias = Annotated[
    ConnectorToolDetailWithoutOutputSchemaResponse | ConnectorToolDetailWithOutputSchemaResponse,
    Field(discriminator="output_schema_status"),
]


class ConnectorDetailResponse(ConnectorMetadata):
    base_capability_description: str
    effective_capability_description: str
    capability_description_override: CapabilityDescriptionOverrideResponse
    publication_status: ConnectorPublicationStatus
    tools: list[ConnectorToolDetailResponse]


class ConnectorListExtensionResponse(Model):
    source: Literal["built-in", "user-supplied"]


class ConnectorListItemResponse(Model):
    id: NonEmptyString
    display_name: NonEmptyString
    description: NonEmptyString
    icon_data_url: str | None = Field(default=None, exclude_if=lambda value: value is None)
    extension: ConnectorListExtensionResponse
    publication_status: ConnectorPublicationStatus
    available_actions: list[Literal["configure", "publish", "unpublish"]]


class ConnectorListResponse(Model):
    connectors: list[ConnectorListItemResponse]


class ConnectorPromptArgumentResponse(Model):
    name: str
    description: str
    required: bool


class ConnectorPromptResponse(Model):
    name: str
    description: str
    arguments: list[ConnectorPromptArgumentResponse]
    activation_status: Literal["enabled", "disabled"] = "disabled"


class ConnectorPromptListResponse(Model):
    prompts: list[ConnectorPromptResponse]
    available_actions: list[Literal["activate"]] = Field(default_factory=list)


class ConnectorResourceResponse(Model):
    kind: Literal["resource", "resource_template"]
    name: str
    description: str
    uri: str
    activation_status: Literal["enabled", "disabled"] = "disabled"


class ConnectorResourceListResponse(Model):
    resources: list[ConnectorResourceResponse]
    available_actions: list[Literal["activate"]] = Field(default_factory=list)


class ConnectorConfigurationConnectorSummary(Model):
    id: NonEmptyString
    display_name: NonEmptyString


class ConnectorConfigurationSchemaResponse(Model):
    fields: list[ConnectorConfigurationField]


class ConnectorConfigurationPageResponse(Model):
    connector: ConnectorConfigurationConnectorSummary
    schema_: ConnectorConfigurationSchemaResponse = Field(alias="schema")
    configuration: dict[str, Any] | None


class ConnectorConfigurationSaveRequest(Model):
    model_config = ConfigDict(extra="forbid")

    configuration: dict[str, Any] = Field(default_factory=dict)


class ConnectorConfigurationSaveResponse(Model):
    connector_id: NonEmptyString
    status: Literal["configured"]
    configuration: dict[str, Any]


__all__ = [
    "CapabilityDescriptionOverrideResponse",
    "ConnectorConfigurationConnectorSummary",
    "ConnectorConfigurationPageResponse",
    "ConnectorConfigurationSaveRequest",
    "ConnectorConfigurationSaveResponse",
    "ConnectorConfigurationSchemaResponse",
    "ConnectorDetailResponse",
    "ConnectorListExtensionResponse",
    "ConnectorListItemResponse",
    "ConnectorListResponse",
    "ConnectorPromptActivationBatchRequest",
    "ConnectorPromptActivationBatchResponse",
    "ConnectorPromptActivationBatchResponseItem",
    "ConnectorPromptArgumentResponse",
    "ConnectorPromptListResponse",
    "ConnectorPromptResponse",
    "ConnectorPublicationResponse",
    "ConnectorResourceActivationBatchRequest",
    "ConnectorResourceActivationBatchResponse",
    "ConnectorResourceActivationBatchResponseItem",
    "ConnectorResourceListResponse",
    "ConnectorResourceResponse",
    "ConnectorToolActivationBatchRequest",
    "ConnectorToolActivationItemResponse",
    "ConnectorToolActivationListResponse",
    "ConnectorToolDetailResponse",
    "ConnectorToolDetailWithOutputSchemaResponse",
    "ConnectorToolDetailWithoutOutputSchemaResponse",
]
