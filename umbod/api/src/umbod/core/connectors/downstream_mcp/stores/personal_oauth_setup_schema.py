from typing import cast

from pydantic import ConfigDict

from umbod.proxies import Model
from umbod.core.persistence import Field, KeyCodec, RowCodec, Table, TableIdentity, TextCodec


class PersonalOAuthSetupRecord(Model):
    model_config = ConfigDict(extra="forbid", frozen=True)

    connector_id: str
    document: str


class PersonalOAuthSetupKey(Model):
    model_config = ConfigDict(extra="forbid", frozen=True)

    connector_id: str


PERSONAL_OAUTH_SETUP_IDENTITY = TableIdentity("downstream_mcp_personal_oauth_setup")
PERSONAL_OAUTH_SETUP_CONNECTOR_ID = Field[PersonalOAuthSetupRecord, str](PERSONAL_OAUTH_SETUP_IDENTITY, "connector_id", TextCodec())
PERSONAL_OAUTH_SETUP_DOCUMENT = Field[PersonalOAuthSetupRecord, str](PERSONAL_OAUTH_SETUP_IDENTITY, "document", TextCodec())
PERSONAL_OAUTH_SETUP_TABLE = Table(
    PERSONAL_OAUTH_SETUP_IDENTITY,
    RowCodec(PersonalOAuthSetupRecord, cast(tuple[Field[PersonalOAuthSetupRecord, object], ...], (PERSONAL_OAUTH_SETUP_CONNECTOR_ID, PERSONAL_OAUTH_SETUP_DOCUMENT))),
    KeyCodec(PersonalOAuthSetupKey, cast(tuple[Field[PersonalOAuthSetupRecord, object], ...], (PERSONAL_OAUTH_SETUP_CONNECTOR_ID,))),
)
