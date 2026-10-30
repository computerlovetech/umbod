from typing import cast

from pydantic import BaseModel

from umbod.core.persistence import (
    Field,
    KeyCodec,
    PydanticJsonCodec,
    RowCodec,
    Table,
    TableIdentity,
    TextCodec,
)
from .models import DirectoryModel, ObservedGroup, StoredUser


class DirectoryKey(DirectoryModel):
    key: str


class UserRecord(DirectoryKey):
    issuer: str
    payload: StoredUser


class GroupRecord(DirectoryKey):
    issuer: str
    claim: str
    payload: ObservedGroup


USER_IDENTITY = TableIdentity("identity_directory_users")
USER_KEY = Field[UserRecord, str](USER_IDENTITY, "key", TextCodec())
USER_ISSUER = Field[UserRecord, str](USER_IDENTITY, "issuer", TextCodec())
USER_PAYLOAD = Field[UserRecord, StoredUser](
    USER_IDENTITY, "payload", PydanticJsonCodec(StoredUser)
)
USER_TABLE = Table(
    USER_IDENTITY,
    RowCodec(
        UserRecord,
        cast(
            tuple[Field[UserRecord, object], ...], (USER_KEY, USER_ISSUER, USER_PAYLOAD)
        ),
    ),
    KeyCodec(DirectoryKey, cast(tuple[Field[UserRecord, object], ...], (USER_KEY,))),
)
GROUP_IDENTITY = TableIdentity("identity_directory_groups")
GROUP_KEY = Field[GroupRecord, str](GROUP_IDENTITY, "key", TextCodec())
GROUP_ISSUER = Field[GroupRecord, str](GROUP_IDENTITY, "issuer", TextCodec())
GROUP_CLAIM = Field[GroupRecord, str](GROUP_IDENTITY, "claim", TextCodec())
GROUP_PAYLOAD = Field[GroupRecord, ObservedGroup](
    GROUP_IDENTITY, "payload", PydanticJsonCodec(ObservedGroup)
)
GROUP_TABLE = Table(
    GROUP_IDENTITY,
    RowCodec(
        GroupRecord,
        cast(
            tuple[Field[GroupRecord, object], ...],
            (GROUP_KEY, GROUP_ISSUER, GROUP_CLAIM, GROUP_PAYLOAD),
        ),
    ),
    KeyCodec(DirectoryKey, cast(tuple[Field[GroupRecord, object], ...], (GROUP_KEY,))),
)
DIRECTORY_TABLES = cast(
    tuple[Table[BaseModel, BaseModel], ...], (USER_TABLE, GROUP_TABLE)
)
