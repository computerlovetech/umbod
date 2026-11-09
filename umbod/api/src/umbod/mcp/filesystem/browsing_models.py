from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from umbod.core.filesystem.browsing.exploration import (
    BrowseTarget,
    DirectoryListing,
    DirectoryTree,
    NodeInspection,
    TreeEntry,
)

from .models import FilesystemNodeSummary


class FilesystemNodeInspection(NodeInspection):
    node: FilesystemNodeSummary


class FilesystemDirectoryListing(DirectoryListing):
    node: FilesystemNodeSummary
    entries: list[FilesystemNodeSummary]


class FilesystemTreeEntry(TreeEntry):
    node: FilesystemNodeSummary


class FilesystemDirectoryTree(DirectoryTree):
    node: FilesystemNodeSummary
    entries: list[FilesystemTreeEntry]


class ResolveHome(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    operation: Literal["home"] = Field(description="Resolve the caller home directory; no target is accepted.")


class BrowseCommand(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    target: BrowseTarget = Field(description="Select the filesystem root, an absolute path, or a node UUID.")


class BoundedBrowseCommand(BrowseCommand):
    max_entries: int = Field(default=100, ge=1, le=1000, strict=True, description="Maximum returned entries, from 1 to 1000; truncated results are indicated.")


class ListDirectory(BoundedBrowseCommand):
    operation: Literal["ls"] = Field(description="List immediate directory children.")


class ReadTree(BoundedBrowseCommand):
    operation: Literal["tree"] = Field(description="Read a bounded directory tree.")
    depth: int = Field(default=2, ge=1, le=16, strict=True, description="Maximum descendant depth, from 1 to 16.")


class InspectNode(BrowseCommand):
    operation: Literal["stat"] = Field(description="Inspect one node and its breadcrumbs without reading file bytes.")


FilesystemBrowseCommand = Annotated[
    Union[ListDirectory, ReadTree, InspectNode, ResolveHome], Field(discriminator="operation")
]


class DirectoryListingResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    operation: Literal["ls"]
    result: FilesystemDirectoryListing


class DirectoryTreeResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    operation: Literal["tree"]
    result: FilesystemDirectoryTree


class NodeInspectionResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    operation: Literal["stat"]
    result: FilesystemNodeInspection


class HomeResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    operation: Literal["home"]
    result: FilesystemNodeInspection


FilesystemBrowseResponse = Annotated[
    Union[DirectoryListingResponse, DirectoryTreeResponse, NodeInspectionResponse, HomeResponse],
    Field(discriminator="operation"),
]

BROWSE_COMMAND = TypeAdapter[FilesystemBrowseCommand](FilesystemBrowseCommand)
BROWSE_RESPONSE = TypeAdapter[FilesystemBrowseResponse](FilesystemBrowseResponse)


def browse_input_schema() -> dict[str, Any]:
    schema = BROWSE_COMMAND.json_schema()
    definitions = schema["$defs"]
    schema["type"] = "object"
    schema["properties"] = {"target": definitions["ListDirectory"]["properties"]["target"]}
    return schema
