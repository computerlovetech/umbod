from typing import cast

from pydantic import BaseModel, ConfigDict

from umbod.core.persistence import Field, KeyCodec, RowCodec, Table, TableIdentity, TextCodec


class PersonalOAuthConfigurationRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    connector_id: str
    revision: str
    document: str


class PersonalOAuthConfigurationKey(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    connector_id: str


PERSONAL_OAUTH_CONFIGURATION_IDENTITY = TableIdentity("downstream_mcp_personal_oauth_configurations")
PERSONAL_OAUTH_CONFIGURATION_CONNECTOR_ID = Field[PersonalOAuthConfigurationRecord, str](
    PERSONAL_OAUTH_CONFIGURATION_IDENTITY, "connector_id", TextCodec()
)
PERSONAL_OAUTH_CONFIGURATION_REVISION = Field[PersonalOAuthConfigurationRecord, str](
    PERSONAL_OAUTH_CONFIGURATION_IDENTITY, "revision", TextCodec()
)
PERSONAL_OAUTH_CONFIGURATION_DOCUMENT = Field[PersonalOAuthConfigurationRecord, str](
    PERSONAL_OAUTH_CONFIGURATION_IDENTITY, "document", TextCodec()
)
_PERSONAL_OAUTH_CONFIGURATION_FIELDS = cast(
    tuple[Field[PersonalOAuthConfigurationRecord, object], ...],
    (PERSONAL_OAUTH_CONFIGURATION_CONNECTOR_ID, PERSONAL_OAUTH_CONFIGURATION_REVISION, PERSONAL_OAUTH_CONFIGURATION_DOCUMENT),
)
PERSONAL_OAUTH_CONFIGURATION_TABLE = Table(
    PERSONAL_OAUTH_CONFIGURATION_IDENTITY,
    RowCodec(PersonalOAuthConfigurationRecord, _PERSONAL_OAUTH_CONFIGURATION_FIELDS),
    KeyCodec(PersonalOAuthConfigurationKey, cast(tuple[Field[PersonalOAuthConfigurationRecord, object], ...], (PERSONAL_OAUTH_CONFIGURATION_CONNECTOR_ID,))),
)
