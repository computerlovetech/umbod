from pydantic import BaseModel, ConfigDict, PositiveInt

from umbod.core.filesystem import NodeMetadata
from umbod.core.filesystem.browsing import NodeSummary


class FilesystemNodeMetadata(NodeMetadata):
    model_config = ConfigDict(extra="forbid", frozen=True)

    def to_core_metadata(self) -> NodeMetadata:
        return NodeMetadata(content_type=self.content_type, attributes=self.attributes)


class CreateNodeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    metadata: FilesystemNodeMetadata


class UploadPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    max_bytes: PositiveInt


class ChildrenResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    nodes: list[NodeSummary]
