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

from .models import (
    PersonalAccessTokenMetadata,
    StoredPersonalAccessToken,
    TokenId,
    TokenModel,
)


class PersonalAccessTokenKey(TokenModel):
    token_id: TokenId


class PersonalAccessTokenRecord(StoredPersonalAccessToken):
    token_id: TokenId
    issuer: str
    subject: str


TOKEN_IDENTITY = TableIdentity("personal_access_tokens")
TOKEN_ID = Field[PersonalAccessTokenRecord, str](
    TOKEN_IDENTITY, "token_id", TextCodec()
)
TOKEN_ISSUER = Field[PersonalAccessTokenRecord, str](
    TOKEN_IDENTITY, "issuer", TextCodec()
)
TOKEN_SUBJECT = Field[PersonalAccessTokenRecord, str](
    TOKEN_IDENTITY, "subject", TextCodec()
)
TOKEN_METADATA = Field[PersonalAccessTokenRecord, PersonalAccessTokenMetadata](
    TOKEN_IDENTITY, "metadata", PydanticJsonCodec(PersonalAccessTokenMetadata)
)
TOKEN_DIGEST = Field[PersonalAccessTokenRecord, str](
    TOKEN_IDENTITY, "digest", TextCodec()
)
TOKEN_TABLE = Table(
    TOKEN_IDENTITY,
    RowCodec(
        PersonalAccessTokenRecord,
        cast(
            tuple[Field[PersonalAccessTokenRecord, object], ...],
            (TOKEN_ID, TOKEN_ISSUER, TOKEN_SUBJECT, TOKEN_METADATA, TOKEN_DIGEST),
        ),
    ),
    KeyCodec(
        PersonalAccessTokenKey,
        cast(tuple[Field[PersonalAccessTokenRecord, object], ...], (TOKEN_ID,)),
    ),
)
PERSONAL_ACCESS_TOKEN_TABLES = cast(
    tuple[Table[BaseModel, BaseModel], ...], (TOKEN_TABLE,)
)
