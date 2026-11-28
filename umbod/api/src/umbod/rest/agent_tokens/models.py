from pydantic import BaseModel, ConfigDict, Field

from umbod.core.agent_tokens import AgentCredentialStatus, IssuedAgentCredential
from umbod.core.agent_tokens.models import NonblankText, UuidHex
from umbod.core.credential_expiry import CredentialExpiry


class RotateAgentTokenRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)

    expires_at: CredentialExpiry


class AgentTokenMetadataResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, frozen=True)

    agent_id: UuidHex
    display_name: NonblankText
    group_id: NonblankText
    credential_id: UuidHex
    expires_at: CredentialExpiry
    status: AgentCredentialStatus


class IssuedAgentTokenResponse(BaseModel):
    metadata: AgentTokenMetadataResponse
    token: str = Field(repr=False)

    @classmethod
    def from_issued(cls, issued: IssuedAgentCredential) -> "IssuedAgentTokenResponse":
        return cls(
            metadata=AgentTokenMetadataResponse.model_validate(issued.metadata),
            token=issued.token.get_secret_value(),
        )
