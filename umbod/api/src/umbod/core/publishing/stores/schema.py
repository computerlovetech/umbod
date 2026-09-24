from typing import cast

from pydantic import BaseModel, ConfigDict

from umbod.core.persistence import (
    BooleanCodec,
    Field,
    IntegerCodec,
    KeyCodec,
    RowCodec,
    TextCodec,
    Fields,
    Table,
    TableIdentity,
)


class PublicationStateRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    connector_id: str
    published: bool
    previously_published: bool
    revision: int
    updated_at: str


class PublicationStateKey(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    connector_id: str


class PublicationStateResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    published: bool
    previously_published: bool
    revision: int
    updated_at: str


class PublicationStateWrite(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    published: bool
    previously_published: bool
    revision: int
    updated_at: str


PUBLICATION_STATE_IDENTITY = TableIdentity("connector_publication_states")
PUBLICATION_STATE_CONNECTOR_ID = Field[PublicationStateRecord, str](
    PUBLICATION_STATE_IDENTITY, "connector_id", TextCodec()
)
PUBLICATION_STATE_PUBLISHED = Field[PublicationStateRecord, bool](
    PUBLICATION_STATE_IDENTITY, "published", BooleanCodec()
)
PUBLICATION_STATE_PREVIOUSLY_PUBLISHED = Field[PublicationStateRecord, bool](
    PUBLICATION_STATE_IDENTITY, "previously_published", BooleanCodec()
)
PUBLICATION_STATE_REVISION = Field[PublicationStateRecord, int](
    PUBLICATION_STATE_IDENTITY, "revision", IntegerCodec()
)
PUBLICATION_STATE_UPDATED_AT = Field[PublicationStateRecord, str](
    PUBLICATION_STATE_IDENTITY, "updated_at", TextCodec()
)
_PUBLICATION_STATE_FIELDS = cast(
    tuple[Field[PublicationStateRecord, object], ...],
    (
        PUBLICATION_STATE_CONNECTOR_ID,
        PUBLICATION_STATE_PUBLISHED,
        PUBLICATION_STATE_PREVIOUSLY_PUBLISHED,
        PUBLICATION_STATE_REVISION,
        PUBLICATION_STATE_UPDATED_AT,
    ),
)
PUBLICATION_STATE_TABLE = Table(
    PUBLICATION_STATE_IDENTITY,
    RowCodec(PublicationStateRecord, _PUBLICATION_STATE_FIELDS),
    KeyCodec(
        PublicationStateKey,
        cast(
            tuple[Field[PublicationStateRecord, object], ...],
            (PUBLICATION_STATE_CONNECTOR_ID,),
        ),
    ),
)
PUBLICATION_STATE_PROJECTION = Fields(
    PublicationStateResult,
    cast(
        tuple[Field[PublicationStateRecord, object], ...],
        (
            PUBLICATION_STATE_PUBLISHED,
            PUBLICATION_STATE_PREVIOUSLY_PUBLISHED,
            PUBLICATION_STATE_REVISION,
            PUBLICATION_STATE_UPDATED_AT,
        ),
    ),
)
PUBLICATION_STATES = PUBLICATION_STATE_TABLE
