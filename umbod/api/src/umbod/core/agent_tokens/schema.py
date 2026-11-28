from typing import Self, cast

from pydantic import model_validator

from umbod.proxies import PydanticModel
from umbod.core.persistence import (
    Field,
    KeyCodec,
    PydanticJsonCodec,
    RowCodec,
    Table,
    TableIdentity,
    TextCodec,
)

from .models import (
    AgentCredentialMetadata,
    AgentTokenModel,
    StoredAgentCredential,
    UuidHex,
)


class AgentCredentialKey(AgentTokenModel):
    agent_id: UuidHex


class AgentCredentialRow(StoredAgentCredential):
    agent_id: UuidHex

    @model_validator(mode="after")
    def require_matching_agent_id(self) -> Self:
        if self.agent_id != self.metadata.agent_id:
            raise ValueError("Agent credential metadata must match the row key")
        return self


AGENT_CREDENTIAL_IDENTITY = TableIdentity("agent_credentials")
AGENT_ID = Field[AgentCredentialRow, str](
    AGENT_CREDENTIAL_IDENTITY, "agent_id", TextCodec()
)
AGENT_METADATA = Field[AgentCredentialRow, AgentCredentialMetadata](
    AGENT_CREDENTIAL_IDENTITY, "metadata", PydanticJsonCodec(AgentCredentialMetadata)
)
AGENT_GROUP_INSTANCE_ID = Field[AgentCredentialRow, str](
    AGENT_CREDENTIAL_IDENTITY, "group_instance_id", TextCodec()
)
AGENT_DIGEST = Field[AgentCredentialRow, str](
    AGENT_CREDENTIAL_IDENTITY, "digest", TextCodec()
)
AGENT_CREDENTIAL_TABLE = Table(
    AGENT_CREDENTIAL_IDENTITY,
    RowCodec(
        AgentCredentialRow,
        cast(
            tuple[Field[AgentCredentialRow, object], ...],
            (AGENT_ID, AGENT_METADATA, AGENT_GROUP_INSTANCE_ID, AGENT_DIGEST),
        ),
    ),
    KeyCodec(
        AgentCredentialKey,
        cast(tuple[Field[AgentCredentialRow, object], ...], (AGENT_ID,)),
    ),
)
AGENT_CREDENTIAL_TABLES = cast(
    tuple[Table[PydanticModel, PydanticModel], ...], (AGENT_CREDENTIAL_TABLE,)
)
