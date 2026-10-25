from datetime import datetime
from enum import StrEnum
from typing import Union
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

NodeId = UUID
StorageKey = str


class NodeKind(StrEnum):
    FILE = "file"
    DIRECTORY = "directory"


class RootParent(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class EmptyContent(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class UnspecifiedContentType(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class ContentRef(BaseModel):
    model_config = ConfigDict(frozen=True)

    key: StorageKey
    size: int = Field(ge=0)


class NodeMetadata(BaseModel):
    model_config = ConfigDict(frozen=True)

    content_type: Union[str, UnspecifiedContentType]
    attributes: dict[str, str]


class Node(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: NodeId
    parent_id: Union[NodeId, RootParent]
    name: str
    kind: NodeKind
    metadata: NodeMetadata
    content: Union[ContentRef, EmptyContent]
    created_at: datetime
    updated_at: datetime
    revision: int = Field(ge=1)
