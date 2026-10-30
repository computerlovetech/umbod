from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from umbod.core.filesystem.browsing import NodeSummary
from umbod.core.filesystem.models import NodeMetadata


class FilesystemNodeMetadata(NodeMetadata):
    model_config = ConfigDict(frozen=True, extra="forbid")


class DeleteFileCommand(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    node_id: UUID
    expected_revision: int = Field(
        ge=1, le=9_999_999_999_999_999_999,
        description="Current file revision from filesystem browsing; deletion fails if it has changed.",
    )


class FileDeletionResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    node_id: UUID
    deleted: Literal[True]


class FilesystemChildren(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    nodes: list[NodeSummary]
