from typing import cast

from pydantic import BaseModel, ConfigDict

from umbod.core.persistence import (
    Field,
    KeyCodec,
    RowCodec,
    Table,
    TableIdentity,
    TextCodec,
)


class PersonalOAuthAttemptRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    attempt_id: str
    namespace: str
    subject: str
    connector_id: str
    document: str


class PersonalOAuthAttemptKey(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    attempt_id: str


PERSONAL_OAUTH_ATTEMPT_IDENTITY = TableIdentity(
    "downstream_mcp_personal_oauth_attempts"
)
PERSONAL_OAUTH_ATTEMPT_ID = Field[PersonalOAuthAttemptRecord, str](
    PERSONAL_OAUTH_ATTEMPT_IDENTITY, "attempt_id", TextCodec()
)
PERSONAL_OAUTH_ATTEMPT_NAMESPACE = Field[PersonalOAuthAttemptRecord, str](
    PERSONAL_OAUTH_ATTEMPT_IDENTITY, "namespace", TextCodec()
)
PERSONAL_OAUTH_ATTEMPT_SUBJECT = Field[PersonalOAuthAttemptRecord, str](
    PERSONAL_OAUTH_ATTEMPT_IDENTITY, "subject", TextCodec()
)
PERSONAL_OAUTH_ATTEMPT_CONNECTOR_ID = Field[PersonalOAuthAttemptRecord, str](
    PERSONAL_OAUTH_ATTEMPT_IDENTITY, "connector_id", TextCodec()
)
PERSONAL_OAUTH_ATTEMPT_DOCUMENT = Field[PersonalOAuthAttemptRecord, str](
    PERSONAL_OAUTH_ATTEMPT_IDENTITY, "document", TextCodec()
)
_PERSONAL_OAUTH_ATTEMPT_FIELDS = cast(
    tuple[Field[PersonalOAuthAttemptRecord, object], ...],
    (
        PERSONAL_OAUTH_ATTEMPT_ID,
        PERSONAL_OAUTH_ATTEMPT_NAMESPACE,
        PERSONAL_OAUTH_ATTEMPT_SUBJECT,
        PERSONAL_OAUTH_ATTEMPT_CONNECTOR_ID,
        PERSONAL_OAUTH_ATTEMPT_DOCUMENT,
    ),
)
PERSONAL_OAUTH_ATTEMPT_TABLE = Table(
    PERSONAL_OAUTH_ATTEMPT_IDENTITY,
    RowCodec(PersonalOAuthAttemptRecord, _PERSONAL_OAUTH_ATTEMPT_FIELDS),
    KeyCodec(
        PersonalOAuthAttemptKey,
        cast(
            tuple[Field[PersonalOAuthAttemptRecord, object], ...],
            (PERSONAL_OAUTH_ATTEMPT_ID,),
        ),
    ),
)
