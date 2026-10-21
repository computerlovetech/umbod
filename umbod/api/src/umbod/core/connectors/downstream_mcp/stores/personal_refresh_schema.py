from typing import cast

from umbod.core.persistence import Field, KeyCodec, RowCodec, Table, TableIdentity, TextCodec

from .schema import PersonalConnectionRecord, PersonalConnectionRecordKey


PERSONAL_REFRESH_IDENTITY = TableIdentity("downstream_mcp_personal_refresh_claims")
PERSONAL_REFRESH_NAMESPACE = Field[PersonalConnectionRecord, str](PERSONAL_REFRESH_IDENTITY, "namespace", TextCodec())
PERSONAL_REFRESH_SUBJECT = Field[PersonalConnectionRecord, str](PERSONAL_REFRESH_IDENTITY, "subject", TextCodec())
PERSONAL_REFRESH_CONNECTOR_ID = Field[PersonalConnectionRecord, str](PERSONAL_REFRESH_IDENTITY, "connector_id", TextCodec())
PERSONAL_REFRESH_DOCUMENT = Field[PersonalConnectionRecord, str](PERSONAL_REFRESH_IDENTITY, "document", TextCodec())
_REFRESH_KEY_FIELDS = cast(tuple[Field[PersonalConnectionRecord, object], ...], (
    PERSONAL_REFRESH_NAMESPACE,
    PERSONAL_REFRESH_SUBJECT,
    PERSONAL_REFRESH_CONNECTOR_ID,
))
PERSONAL_REFRESH_TABLE = Table(
    PERSONAL_REFRESH_IDENTITY,
    RowCodec(PersonalConnectionRecord, (*_REFRESH_KEY_FIELDS, PERSONAL_REFRESH_DOCUMENT)),
    KeyCodec(PersonalConnectionRecordKey, _REFRESH_KEY_FIELDS),
)
