from typing import cast

from pydantic import BaseModel, Field as ModelField

from umbod.core.persistence import Field, KeyCodec, RowCodec, Table, TableIdentity, TextCodec


class DraftKey(BaseModel):
    draft_id: str


class DraftRow(DraftKey):
    issuer: str = ModelField(repr=False)
    subject: str = ModelField(repr=False)
    head_revision_id: str


class RevisionKey(BaseModel):
    draft_id: str
    revision_id: str


class RevisionRow(RevisionKey):
    source: str = ModelField(repr=False)
    source_sha256: str


_DRAFT = TableIdentity("portable_connector_drafts")
DRAFT_ID = Field[DraftRow, str](_DRAFT, "draft_id", TextCodec())
AUTHOR_ISSUER = Field[DraftRow, str](_DRAFT, "issuer", TextCodec())
AUTHOR_SUBJECT = Field[DraftRow, str](_DRAFT, "subject", TextCodec())
_HEAD = Field[DraftRow, str](_DRAFT, "head_revision_id", TextCodec())
DRAFT_TABLE = Table(
    _DRAFT,
    RowCodec(DraftRow, cast(tuple[Field[DraftRow, object], ...], (DRAFT_ID, AUTHOR_ISSUER, AUTHOR_SUBJECT, _HEAD))),
    KeyCodec(DraftKey, cast(tuple[Field[DraftRow, object], ...], (DRAFT_ID,))),
)

_REVISION = TableIdentity("portable_connector_revisions")
REVISION_DRAFT_ID = Field[RevisionRow, str](_REVISION, "draft_id", TextCodec())
REVISION_ID = Field[RevisionRow, str](_REVISION, "revision_id", TextCodec())
_SOURCE = Field[RevisionRow, str](_REVISION, "source", TextCodec())
_HASH = Field[RevisionRow, str](_REVISION, "source_sha256", TextCodec())
REVISION_TABLE = Table(
    _REVISION,
    RowCodec(RevisionRow, cast(tuple[Field[RevisionRow, object], ...], (REVISION_DRAFT_ID, REVISION_ID, _SOURCE, _HASH))),
    KeyCodec(RevisionKey, cast(tuple[Field[RevisionRow, object], ...], (REVISION_DRAFT_ID, REVISION_ID))),
)

PORTABLE_CONNECTOR_DRAFT_TABLES = cast(tuple[Table[BaseModel, BaseModel], ...], (DRAFT_TABLE, REVISION_TABLE))
