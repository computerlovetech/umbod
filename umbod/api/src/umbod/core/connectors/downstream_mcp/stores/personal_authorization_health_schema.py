from typing import cast

from umbod.core.persistence import Field, KeyCodec, RowCodec, Table, TableIdentity, TextCodec

from .schema import PersonalConnectionRecord, PersonalConnectionRecordKey


PERSONAL_AUTHORIZATION_REJECTION_IDENTITY = TableIdentity("downstream_mcp_personal_authorization_rejections")
PERSONAL_AUTHORIZATION_REJECTION_NAMESPACE = Field[PersonalConnectionRecord, str](PERSONAL_AUTHORIZATION_REJECTION_IDENTITY, "namespace", TextCodec())
PERSONAL_AUTHORIZATION_REJECTION_SUBJECT = Field[PersonalConnectionRecord, str](PERSONAL_AUTHORIZATION_REJECTION_IDENTITY, "subject", TextCodec())
PERSONAL_AUTHORIZATION_REJECTION_CONNECTOR_ID = Field[PersonalConnectionRecord, str](PERSONAL_AUTHORIZATION_REJECTION_IDENTITY, "connector_id", TextCodec())
PERSONAL_AUTHORIZATION_REJECTION_DOCUMENT = Field[PersonalConnectionRecord, str](PERSONAL_AUTHORIZATION_REJECTION_IDENTITY, "document", TextCodec())
_REJECTION_KEY_FIELDS = cast(tuple[Field[PersonalConnectionRecord, object], ...], (
    PERSONAL_AUTHORIZATION_REJECTION_NAMESPACE,
    PERSONAL_AUTHORIZATION_REJECTION_SUBJECT,
    PERSONAL_AUTHORIZATION_REJECTION_CONNECTOR_ID,
))
PERSONAL_AUTHORIZATION_REJECTION_TABLE = Table(
    PERSONAL_AUTHORIZATION_REJECTION_IDENTITY,
    RowCodec(PersonalConnectionRecord, (*_REJECTION_KEY_FIELDS, PERSONAL_AUTHORIZATION_REJECTION_DOCUMENT)),
    KeyCodec(PersonalConnectionRecordKey, _REJECTION_KEY_FIELDS),
)
