from typing import cast

from pydantic import BaseModel, ConfigDict

from umbod.core.persistence import (
    Field,
    IntegerCodec,
    KeyCodec,
    RowCodec,
    Table,
    TableIdentity,
    TextCodec,
)


class MessagingEventRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    sequence: int
    event_type: str
    document: str


class MessagingEventKey(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    sequence: int


class MessagingCheckpointRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    consumer_id: str
    sequence: int


class MessagingCheckpointKey(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    consumer_id: str


_EVENT_IDENTITY = TableIdentity("messaging_events")
EVENT_SEQUENCE = Field[MessagingEventRecord, int](_EVENT_IDENTITY, "sequence", IntegerCodec())
EVENT_TYPE = Field[MessagingEventRecord, str](_EVENT_IDENTITY, "event_type", TextCodec())
EVENT_DOCUMENT = Field[MessagingEventRecord, str](_EVENT_IDENTITY, "document", TextCodec())
EVENT_TABLE = Table(
    _EVENT_IDENTITY,
    RowCodec(
        MessagingEventRecord,
        cast(
            tuple[Field[MessagingEventRecord, object], ...],
            (EVENT_SEQUENCE, EVENT_TYPE, EVENT_DOCUMENT),
        ),
    ),
    KeyCodec(
        MessagingEventKey, cast(tuple[Field[MessagingEventRecord, object], ...], (EVENT_SEQUENCE,))
    ),
)

_CHECKPOINT_IDENTITY = TableIdentity("messaging_checkpoints")
CHECKPOINT_CONSUMER_ID = Field[MessagingCheckpointRecord, str](
    _CHECKPOINT_IDENTITY, "consumer_id", TextCodec()
)
CHECKPOINT_SEQUENCE = Field[MessagingCheckpointRecord, int](
    _CHECKPOINT_IDENTITY, "sequence", IntegerCodec()
)
CHECKPOINT_TABLE = Table(
    _CHECKPOINT_IDENTITY,
    RowCodec(
        MessagingCheckpointRecord,
        cast(
            tuple[Field[MessagingCheckpointRecord, object], ...],
            (CHECKPOINT_CONSUMER_ID, CHECKPOINT_SEQUENCE),
        ),
    ),
    KeyCodec(
        MessagingCheckpointKey,
        cast(tuple[Field[MessagingCheckpointRecord, object], ...], (CHECKPOINT_CONSUMER_ID,)),
    ),
)

__all__ = [
    "CHECKPOINT_CONSUMER_ID",
    "CHECKPOINT_SEQUENCE",
    "CHECKPOINT_TABLE",
    "EVENT_DOCUMENT",
    "EVENT_SEQUENCE",
    "EVENT_TABLE",
    "EVENT_TYPE",
    "MessagingCheckpointKey",
    "MessagingCheckpointRecord",
    "MessagingEventKey",
    "MessagingEventRecord",
]
