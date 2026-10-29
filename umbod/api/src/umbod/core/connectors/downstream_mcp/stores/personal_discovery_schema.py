from typing import cast

from umbod.core.persistence import Field, KeyCodec, RowCodec, Table, TableIdentity, TextCodec

from .schema import PersonalConnectionRecord, PersonalConnectionRecordKey

PERSONAL_DISCOVERY_IDENTITY = TableIdentity("downstream_mcp_personal_discovery")
PERSONAL_DISCOVERY_NAMESPACE = Field[PersonalConnectionRecord, str](PERSONAL_DISCOVERY_IDENTITY, "namespace", TextCodec())
PERSONAL_DISCOVERY_SUBJECT = Field[PersonalConnectionRecord, str](PERSONAL_DISCOVERY_IDENTITY, "subject", TextCodec())
PERSONAL_DISCOVERY_CONNECTOR_ID = Field[PersonalConnectionRecord, str](PERSONAL_DISCOVERY_IDENTITY, "connector_id", TextCodec())
PERSONAL_DISCOVERY_DOCUMENT = Field[PersonalConnectionRecord, str](PERSONAL_DISCOVERY_IDENTITY, "document", TextCodec())
_KEY_FIELDS = cast(tuple[Field[PersonalConnectionRecord, object], ...], (PERSONAL_DISCOVERY_NAMESPACE, PERSONAL_DISCOVERY_SUBJECT, PERSONAL_DISCOVERY_CONNECTOR_ID))
PERSONAL_DISCOVERY_TABLE = Table(PERSONAL_DISCOVERY_IDENTITY, RowCodec(PersonalConnectionRecord, (*_KEY_FIELDS, PERSONAL_DISCOVERY_DOCUMENT)), KeyCodec(PersonalConnectionRecordKey, _KEY_FIELDS))
