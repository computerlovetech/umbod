from typing import Annotated, Literal, Union
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from umbod.core.filesystem.browsing import NodeSummary
from umbod.core.filesystem.models import NodeMetadata
from umbod.core.filesystem.sharing import SharingGrantSummary


class AuthorizedSharingMetadata(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    can_share: Literal[True]
    grants: tuple[SharingGrantSummary, ...]


class RestrictedSharingMetadata(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    can_share: Literal[False]


SharingMetadata = Annotated[
    Union[AuthorizedSharingMetadata, RestrictedSharingMetadata], Field(discriminator="can_share"),
]


class FilesystemNodeSummary(NodeSummary):
    model_config = ConfigDict(frozen=True, extra="forbid")

    sharing: SharingMetadata


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

    nodes: list[FilesystemNodeSummary]
