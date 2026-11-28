from enum import StrEnum
from typing import Annotated, Literal, Self

from pydantic import (
    AfterValidator,
    ConfigDict,
    Field,
    SecretStr,
    StringConstraints,
    model_validator,
)

from umbod.proxies import Model
from umbod.core.credential_expiry import CredentialExpiry
from umbod.core.groups.models import GroupInstanceId


def _nonblank(value: str) -> str:
    if not value.strip():
        raise ValueError("Value must not be blank")
    return value


NonblankText = Annotated[str, StringConstraints(strict=True), AfterValidator(_nonblank)]
UuidHex = Annotated[
    str,
    StringConstraints(
        strict=True, min_length=32, max_length=32, pattern=r"^[0-9a-f]{32}$"
    ),
]


class AgentTokenModel(Model):
    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)


class CreateAgent(AgentTokenModel):
    display_name: NonblankText
    group_id: NonblankText
    expires_at: CredentialExpiry


class RotateAgentCredential(AgentTokenModel):
    agent_id: UuidHex
    expires_at: CredentialExpiry


class AgentCredentialStatus(StrEnum):
    ACTIVE = "active"
    EXPIRED = "expired"
    REVOKED = "revoked"


class AgentCredentialMetadata(AgentTokenModel):
    agent_id: UuidHex
    display_name: NonblankText
    group_id: NonblankText
    credential_id: UuidHex
    expires_at: CredentialExpiry
    status: AgentCredentialStatus

    @model_validator(mode="after")
    def require_independent_ids(self) -> Self:
        if self.agent_id == self.credential_id:
            raise ValueError("Agent and credential IDs must differ")
        return self


class IssuedAgentCredential(AgentTokenModel):
    metadata: AgentCredentialMetadata
    token: SecretStr = Field(repr=False, exclude=True)


class PublicMcpAgentIdentity(AgentTokenModel):
    agent_id: UuidHex
    group_id: NonblankText
    group_instance_id: GroupInstanceId
    audience: Literal["umbod:mcp"]


class StoredAgentCredential(AgentTokenModel):
    metadata: AgentCredentialMetadata
    group_instance_id: GroupInstanceId
    digest: Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")] = Field(
        repr=False, exclude=True
    )
