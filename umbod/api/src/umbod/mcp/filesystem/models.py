from pydantic import BaseModel, ConfigDict

from umbod.core.filesystem.browsing import NodeSummary
from umbod.core.filesystem.models import NodeMetadata


class FilesystemNodeMetadata(NodeMetadata):
    model_config = ConfigDict(frozen=True, extra="forbid")


class FilesystemChildren(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    nodes: list[NodeSummary]
