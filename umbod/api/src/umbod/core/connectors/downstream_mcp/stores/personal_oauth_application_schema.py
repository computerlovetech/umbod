from typing import cast

from pydantic import BaseModel, ConfigDict

from umbod.core.persistence import Field, KeyCodec, RowCodec, Table, TableIdentity, TextCodec


class PersonalOAuthApplicationRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    connector_id: str
    registration_id: str
    document: str


class PersonalOAuthApplicationKey(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    registration_id: str


PERSONAL_OAUTH_APPLICATION_IDENTITY = TableIdentity("downstream_mcp_personal_oauth_applications")
PERSONAL_OAUTH_APPLICATION_CONNECTOR_ID = Field[PersonalOAuthApplicationRecord, str](
    PERSONAL_OAUTH_APPLICATION_IDENTITY, "connector_id", TextCodec()
)
PERSONAL_OAUTH_APPLICATION_REGISTRATION_ID = Field[PersonalOAuthApplicationRecord, str](
    PERSONAL_OAUTH_APPLICATION_IDENTITY, "registration_id", TextCodec()
)
PERSONAL_OAUTH_APPLICATION_DOCUMENT = Field[PersonalOAuthApplicationRecord, str](
    PERSONAL_OAUTH_APPLICATION_IDENTITY, "document", TextCodec()
)
_PERSONAL_OAUTH_APPLICATION_FIELDS = cast(
    tuple[Field[PersonalOAuthApplicationRecord, object], ...],
    (PERSONAL_OAUTH_APPLICATION_CONNECTOR_ID, PERSONAL_OAUTH_APPLICATION_REGISTRATION_ID, PERSONAL_OAUTH_APPLICATION_DOCUMENT),
)
PERSONAL_OAUTH_APPLICATION_TABLE = Table(
    PERSONAL_OAUTH_APPLICATION_IDENTITY,
    RowCodec(PersonalOAuthApplicationRecord, _PERSONAL_OAUTH_APPLICATION_FIELDS),
    KeyCodec(PersonalOAuthApplicationKey, cast(tuple[Field[PersonalOAuthApplicationRecord, object], ...], (PERSONAL_OAUTH_APPLICATION_REGISTRATION_ID,))),
)
