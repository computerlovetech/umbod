from typing import Annotated, Literal, Union

from pydantic import ConfigDict, Field, model_validator

from umbod.core.capabilities.descriptions import CapabilityDescription
from umbod.proxies import Model

ConnectorPublicationStatus = Literal["unconfigured", "draft", "published", "unpublished"]
ConnectorActivationStatus = Literal["enabled", "disabled"]
ConnectorInvocationMode = Literal["direct", "ask"]


class SystemInitialCapabilityDescriptionOverride(Model):
    state: Literal["system"] = "system"


class OverriddenInitialCapabilityDescriptionOverride(Model):
    state: Literal["overridden"] = "overridden"
    description: CapabilityDescription


InitialCapabilityDescriptionOverride = Annotated[
    Union[SystemInitialCapabilityDescriptionOverride, OverriddenInitialCapabilityDescriptionOverride],
    Field(discriminator="state"),
]


class CapabilityDescriptionOverrideResponse(Model):
    state: Literal["system", "overridden"]
    revision: int


class ConnectorToolInvocationPolicyItemResponse(Model):
    tool_id: str = Field(min_length=1)
    mode: ConnectorInvocationMode
    revision: int = Field(ge=0)


class ConnectorToolInvocationPolicyListResponse(Model):
    connector_kind: Literal["native", "openapi", "downstream_mcp"]
    connector_id: str = Field(min_length=1)
    tools: list[ConnectorToolInvocationPolicyItemResponse]


class ConnectorToolInvocationPolicyConflictItemResponse(Model):
    tool_id: str = Field(min_length=1)
    expected_revision: int = Field(ge=0)
    current_mode: ConnectorInvocationMode
    current_revision: int = Field(ge=0)


class ConnectorToolInvocationPolicyConflictResponse(Model):
    code: Literal["invocation_policy_revision_conflict"]
    conflicts: list[ConnectorToolInvocationPolicyConflictItemResponse]


class ToolActivationBatchRequestItem(Model):
    model_config = ConfigDict(extra="forbid")

    tool_id: str = Field(min_length=1)
    activation_status: ConnectorActivationStatus | None = None
    invocation_mode: ConnectorInvocationMode | None = None
    expected_policy_revision: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def update_is_valid(self) -> "ToolActivationBatchRequestItem":
        if self.activation_status is None and self.invocation_mode is None:
            raise ValueError("at least one change is required")
        if self.invocation_mode is None and self.expected_policy_revision is not None:
            raise ValueError("expected_policy_revision requires invocation_mode")
        if self.invocation_mode is not None and self.expected_policy_revision is None:
            raise ValueError("expected_policy_revision is required with invocation_mode")
        return self


class ToolActivationBatchRequest(Model):
    model_config = ConfigDict(extra="forbid")

    tools: list[ToolActivationBatchRequestItem] = Field(min_length=1)

    @model_validator(mode="after")
    def tool_ids_are_unique(self) -> "ToolActivationBatchRequest":
        tool_ids = [tool.tool_id for tool in self.tools]
        if len(tool_ids) != len(set(tool_ids)):
            raise ValueError("tool_id values must be unique")
        return self


class ToolActivationBatchResponseItem(Model):
    model_config = ConfigDict(extra="forbid")

    tool_id: str = Field(min_length=1)
    activation_status: ConnectorActivationStatus
    invocation_mode: ConnectorInvocationMode
    policy_revision: int = Field(ge=0)


class ToolActivationBatchResponse(Model):
    model_config = ConfigDict(extra="forbid")

    connector_id: str = Field(min_length=1)
    tools: list[ToolActivationBatchResponseItem]


class PromptActivationBatchRequestItem(Model):
    model_config = ConfigDict(extra="forbid")

    prompt_id: str = Field(min_length=1)
    activation_status: ConnectorActivationStatus


class PromptActivationBatchRequest(Model):
    model_config = ConfigDict(extra="forbid")

    prompts: list[PromptActivationBatchRequestItem] = Field(min_length=1)


class PromptActivationBatchResponseItem(Model):
    model_config = ConfigDict(extra="forbid")

    prompt_id: str = Field(min_length=1)
    activation_status: ConnectorActivationStatus


class PromptActivationBatchResponse(Model):
    model_config = ConfigDict(extra="forbid")

    connector_id: str = Field(min_length=1)
    prompts: list[PromptActivationBatchResponseItem]


class ResourceActivationBatchRequestItem(Model):
    model_config = ConfigDict(extra="forbid")

    resource_id: str = Field(min_length=1)
    kind: Literal["resource", "resource_template"]
    activation_status: ConnectorActivationStatus


class ResourceActivationBatchRequest(Model):
    model_config = ConfigDict(extra="forbid")

    resources: list[ResourceActivationBatchRequestItem] = Field(min_length=1)


class ResourceActivationBatchResponseItem(Model):
    model_config = ConfigDict(extra="forbid")

    resource_id: str = Field(min_length=1)
    kind: Literal["resource", "resource_template"]
    activation_status: ConnectorActivationStatus


class ResourceActivationBatchResponse(Model):
    model_config = ConfigDict(extra="forbid")

    connector_id: str = Field(min_length=1)
    resources: list[ResourceActivationBatchResponseItem]


class ConnectorPublicationResponse(Model):
    connector_id: str = Field(min_length=1)
    publication_status: Literal["published", "unpublished"]
