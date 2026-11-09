from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ...models import AccessGrant, Node, NodeId, Ownership
from ..models import Breadcrumbs, NodeSummary


class ExplorationModel(BaseModel):
    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")


class RootTarget(ExplorationModel):
    type: Literal["root"]


class PathTarget(ExplorationModel):
    type: Literal["path"]
    path: str = Field(
        max_length=4096,
        json_schema_extra={"pattern": r"^/[^\u0000]*$"},
        description="Absolute filesystem path of at most 4096 characters and 64 nonempty slash-separated segments. No . or .. segments or NUL. Repeated and trailing slashes are allowed.",
    )

    @field_validator("path")
    @classmethod
    def validate_path(cls, value: str) -> str:
        segments = [segment for segment in value.split("/") if segment]
        if not value.startswith("/") or "\x00" in value:
            raise ValueError("Expected an absolute filesystem path without NUL")
        if len(segments) > 64 or any(segment in {".", ".."} for segment in segments):
            raise ValueError("Invalid filesystem path segments")
        return value


class NodeTarget(ExplorationModel):
    type: Literal["node"]
    node_id: NodeId


Target = Annotated[Union[RootTarget, PathTarget, NodeTarget], Field(discriminator="type")]


class ListingLimits(ExplorationModel):
    max_entries: int = Field(ge=1, le=1000)


class TreeLimits(ListingLimits):
    depth: int = Field(ge=1, le=16)


class NodeInspection(ExplorationModel):
    node: NodeSummary
    breadcrumbs: Breadcrumbs


class DirectoryListing(NodeInspection):
    entries: list[NodeSummary]
    truncated: bool


class NodeCapabilities(ExplorationModel):
    node_id: NodeId
    rename: bool
    move: bool
    edit_description: bool
    delete: bool
    share: bool
    upload: bool
    create_directory: bool


class BrowseResult(DirectoryListing):
    capabilities: list[NodeCapabilities]


class BrowseScope(ExplorationModel):
    nodes: tuple[Node, ...]
    ownerships: tuple[Ownership, ...]
    grants: tuple[AccessGrant, ...]


class TreeEntry(ExplorationModel):
    node: NodeSummary
    depth: int = Field(ge=1)
    expansion: Literal["file", "expanded", "depth_limit", "entry_limit"]


class DirectoryTree(NodeInspection):
    entries: list[TreeEntry]
    expansion: Literal["expanded", "entry_limit"]
