from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from umbod.core.filesystem.browsing.exploration import (
    BrowseTarget,
    DirectoryListing,
    DirectoryTree,
    NodeInspection,
)


class BrowseCommand(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    target: BrowseTarget


class BoundedBrowseCommand(BrowseCommand):
    max_entries: int = Field(default=100, ge=1, le=1000, strict=True)


class ListDirectory(BoundedBrowseCommand):
    operation: Literal["ls"]


class ReadTree(BoundedBrowseCommand):
    operation: Literal["tree"]
    depth: int = Field(default=2, ge=1, le=16, strict=True)


class InspectNode(BrowseCommand):
    operation: Literal["stat"]


FilesystemBrowseCommand = Annotated[
    Union[ListDirectory, ReadTree, InspectNode], Field(discriminator="operation")
]


class DirectoryListingResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    operation: Literal["ls"]
    result: DirectoryListing


class DirectoryTreeResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    operation: Literal["tree"]
    result: DirectoryTree


class NodeInspectionResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    operation: Literal["stat"]
    result: NodeInspection


FilesystemBrowseResponse = Annotated[
    Union[DirectoryListingResponse, DirectoryTreeResponse, NodeInspectionResponse],
    Field(discriminator="operation"),
]

BROWSE_COMMAND = TypeAdapter[FilesystemBrowseCommand](FilesystemBrowseCommand)
BROWSE_RESPONSE = TypeAdapter[FilesystemBrowseResponse](FilesystemBrowseResponse)


def browse_input_schema() -> dict[str, Any]:
    schema = BROWSE_COMMAND.json_schema()
    definitions = schema["$defs"]
    schema["type"] = "object"
    schema["properties"] = {"target": definitions["ListDirectory"]["properties"]["target"]}
    for reference in schema["oneOf"]:
        definition = definitions[reference["$ref"].rsplit("/", 1)[1]]
        definition["properties"]["target"] = {}
    return schema
