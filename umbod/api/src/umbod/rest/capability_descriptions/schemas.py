from typing import Annotated, Literal, Union

from pydantic import ConfigDict, Field

from umbod.core.capabilities.descriptions import (
    CapabilityDescription,
    ConnectorKind,
)
from umbod.proxies import Model


class ApiModel(Model):
    model_config = ConfigDict(extra="forbid")


class SetOverrideRequest(ApiModel):
    action: Literal["set"]
    description: CapabilityDescription
    expected_revision: Annotated[int, Field(ge=0)]


class ClearOverrideRequest(ApiModel):
    action: Literal["clear"]
    expected_revision: Annotated[int, Field(ge=0)]


OverrideRequest = Annotated[
    Union[SetOverrideRequest, ClearOverrideRequest], Field(discriminator="action")
]


class SystemOverrideResponse(ApiModel):
    state: Literal["system"]
    revision: Annotated[int, Field(ge=0)]


class OverriddenOverrideResponse(ApiModel):
    state: Literal["overridden"]
    description: CapabilityDescription
    revision: Annotated[int, Field(ge=1)]


OverrideResponse = Annotated[
    Union[SystemOverrideResponse, OverriddenOverrideResponse], Field(discriminator="state")
]


class CapabilityDescriptionResponse(ApiModel):
    connector_kind: ConnectorKind
    connector_id: str
    base_description: CapabilityDescription
    effective_description: CapabilityDescription
    override: OverrideResponse


class RevisionConflictResponse(ApiModel):
    code: Literal["capability_description_revision_conflict"]
    current: CapabilityDescriptionResponse
