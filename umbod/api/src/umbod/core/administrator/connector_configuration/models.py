from typing import Annotated, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class AdministratorPrincipal(_StrictModel):
    memberships: tuple[str, ...]


class ConnectorReference(_StrictModel):
    connector_kind: Literal["native", "openapi", "downstream_mcp"]
    connector_id: str = Field(min_length=1)


class InvocationPolicyState(_StrictModel):
    mode: Literal["direct", "ask"]
    revision: int = Field(ge=0)


class CapabilityState(_StrictModel):
    capability_kind: Literal["tool", "prompt", "resource", "resource_template"]
    capability_key: str
    activation_status: Literal["enabled", "disabled"]
    invocation_policy: Optional[InvocationPolicyState] = None


class SystemDescriptionState(_StrictModel):
    state: Literal["system"]
    revision: int = Field(ge=0)


class OverriddenDescriptionState(_StrictModel):
    state: Literal["overridden"]
    description: str
    revision: int = Field(ge=0)


CapabilityDescriptionState = Annotated[
    Union[SystemDescriptionState, OverriddenDescriptionState],
    Field(discriminator="state"),
]


class CapabilityPermissionState(_StrictModel):
    capability_kind: Literal["tool", "prompt", "resource", "resource_template"]
    capability_key: str
    status: Literal["enabled", "disabled"]


class GroupPermissionState(_StrictModel):
    group_id: str
    connector_status: Literal["enabled", "disabled"]
    capabilities: tuple[CapabilityPermissionState, ...]


class ConnectorConfigurableState(_StrictModel):
    connector: ConnectorReference
    capabilities: tuple[CapabilityState, ...] = ()
    capability_description: CapabilityDescriptionState
    group_permissions: tuple[GroupPermissionState, ...] = ()


class CapabilityPermissionDesiredState(_StrictModel):
    capability_kind: Literal["tool", "prompt", "resource", "resource_template"]
    capability_key: str = Field(min_length=1)
    status: Literal["enabled", "disabled"]


class SetCapabilityActivation(_StrictModel):
    operation: Literal["set_capability_activation"]
    capability_kind: Literal["tool", "prompt", "resource", "resource_template"]
    capability_key: str = Field(min_length=1)
    activation_status: Literal["enabled", "disabled"]


class SetCapabilityInvocationPolicy(_StrictModel):
    operation: Literal["set_capability_invocation_policy"]
    capability_kind: Literal["tool", "prompt", "resource", "resource_template"]
    capability_key: str = Field(min_length=1)
    mode: Literal["direct", "ask"]
    expected_revision: int = Field(ge=0)


class SetCapabilityDescription(_StrictModel):
    operation: Literal["set_capability_description"]
    description: str = Field(min_length=1)
    expected_revision: int = Field(ge=0)


class UseSystemCapabilityDescription(_StrictModel):
    operation: Literal["use_system_capability_description"]
    expected_revision: int = Field(ge=0)


class UpdateGroupPermissions(_StrictModel):
    operation: Literal["update_group_permissions"]
    group_id: str = Field(min_length=1)
    connector_status: Optional[Literal["enabled", "disabled"]] = None
    capabilities: tuple[CapabilityPermissionDesiredState, ...] = ()


ConnectorConfigurationOperation = Annotated[
    Union[
        SetCapabilityActivation,
        SetCapabilityInvocationPolicy,
        SetCapabilityDescription,
        UseSystemCapabilityDescription,
        UpdateGroupPermissions,
    ],
    Field(discriminator="operation"),
]


class ConnectorDesiredState(_StrictModel):
    operations: tuple[ConnectorConfigurationOperation, ...] = ()

    def is_empty(self) -> bool:
        return not self.operations
