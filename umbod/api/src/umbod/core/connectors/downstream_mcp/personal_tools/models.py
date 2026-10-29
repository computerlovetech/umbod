import json
from typing import Annotated, Literal

from pydantic import AwareDatetime, Field, model_validator

from umbod.core.capabilities.domain import CapabilityIdentity
from umbod.core.capabilities.tools.names import PublicToolIdentity

from ..models import ConnectorDefinition, ConnectorDefinitionModel, DiscoveredTool, DomainModel, ValidatedJsonObject
from ..personal_connections.models import CanonicalPrincipal, PersonalConnectionKey
from ..personal_connections.runtime_models import PersonalRuntimeAuthorizationQuery, PersonalRuntimeTarget
from .contract_validation import PersonalToolPolicyInvalid, validate_contract_schema


class PersonalToolDiscoveryQuery(DomainModel):
    principal: CanonicalPrincipal
    definitions: tuple[ConnectorDefinitionModel, ...]
    now: AwareDatetime


class InvokePersonalTool(DomainModel):
    identity: CapabilityIdentity
    inventory_revision: str = Field(min_length=1)
    fingerprint: str = Field(pattern="^[0-9a-f]{64}$")
    arguments: ValidatedJsonObject


class PersonalToolPolicyUnavailable(ValueError):
    pass


class PersonalToolPolicyConflict(ValueError):
    pass


class PersonalToolPolicy(DomainModel):
    connector_id: str = Field(min_length=1)
    revision: str = Field(min_length=1)
    approved_at: AwareDatetime
    tools: tuple[DiscoveredTool, ...] = Field(max_length=256)

    @model_validator(mode="after")
    def validate_tools(self) -> "PersonalToolPolicy":
        _validate_tools(self.connector_id, self.tools)
        return self


class UnconfiguredPersonalToolPolicy(DomainModel):
    connector_id: str = Field(min_length=1)
    revision: Literal["unconfigured"] = "unconfigured"
    tools: tuple[DiscoveredTool, ...] = Field(max_length=0)


class ReplacePersonalToolPolicy(DomainModel):
    connector_id: str = Field(min_length=1)
    expected_revision: str = Field(min_length=1)
    tools: tuple[DiscoveredTool, ...] = Field(max_length=256)
    native_identities: tuple[PublicToolIdentity, ...]

    @model_validator(mode="after")
    def validate_tools(self) -> "ReplacePersonalToolPolicy":
        _validate_tools(self.connector_id, self.tools)
        return self


def _validate_tools(connector_id: str, tools: tuple[DiscoveredTool, ...]) -> None:
    names = tuple(tool.identity.downstream_name for tool in tools)
    if len(set(names)) != len(names):
        raise PersonalToolPolicyInvalid("Duplicate tool name")
    for tool in tools:
        if tool.identity.connector_id != connector_id or len(tool.identity.downstream_name) > 128:
            raise PersonalToolPolicyInvalid("Invalid tool identity")
        if len(tool.model_dump_json().encode()) > 131072:
            raise PersonalToolPolicyInvalid("Tool metadata exceeds size limit")
        json.dumps(tool.model_dump(mode="json"), allow_nan=False)
        validate_contract_schema(tool.input_schema)
        if tool.output_schema_status == "present":
            validate_contract_schema(tool.output_schema)


class PersonalToolGrantRevocation(DomainModel):
    group_id: str = Field(min_length=1)
    capability_key: str = Field(min_length=1)


class PersonalToolPolicyReplacement(DomainModel):
    policy: PersonalToolPolicy
    changed_tools: tuple[str, ...]
    revoked_grants: tuple[PersonalToolGrantRevocation, ...]


class MissingInventoryRevision(DomainModel):
    kind: Literal["missing"]


class PresentInventoryRevision(DomainModel):
    kind: Literal["present"]
    revision: str = Field(min_length=1)


PersonalInventoryRevision = Annotated[MissingInventoryRevision | PresentInventoryRevision, Field(discriminator="kind")]


class PersonalToolObservation(DomainModel):
    version: Literal[2]
    key: PersonalConnectionKey
    authorization_revision: str = Field(min_length=1)
    configuration_revision: str = Field(min_length=1)
    inventory_revision: str = Field(min_length=1)
    tools: tuple[DiscoveredTool, ...] = Field(max_length=256)
    expires_at: AwareDatetime

    @model_validator(mode="after")
    def validate_tools(self) -> "PersonalToolObservation":
        _validate_tools(self.key.connector_id, self.tools)
        return self


class SavePersonalToolObservation(DomainModel):
    query: PersonalRuntimeAuthorizationQuery
    target: PersonalRuntimeTarget
    expected_inventory_revision: PersonalInventoryRevision
    tools: tuple[DiscoveredTool, ...] = Field(max_length=256)
    expires_at: AwareDatetime

    @model_validator(mode="after")
    def validate_tools(self) -> "SavePersonalToolObservation":
        _validate_tools(self.query.key.connector_id, self.tools)
        return self


class PersonalToolRecord(DomainModel):
    definition: ConnectorDefinition
    tool: DiscoveredTool
    inventory_revision: str = Field(min_length=1)
    fingerprint: str = Field(pattern="^[0-9a-f]{64}$")


class AdmitPersonalTool(DomainModel):
    query: PersonalRuntimeAuthorizationQuery
    identity: CapabilityIdentity
    inventory_revision: str = Field(min_length=1)
    fingerprint: str = Field(pattern="^[0-9a-f]{64}$")


class PersonalToolAdmission(DomainModel):
    target: PersonalRuntimeTarget
    tool: DiscoveredTool


class PersonalToolDiscoveryResult(DomainModel):
    status: Literal["observed"]
    tool_count: int = Field(ge=0, le=256)
