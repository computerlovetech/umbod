from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field

from umbod.core.filesystem.access import CallerNodeSummary
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


class FilesystemViewNodeSummary(CallerNodeSummary):
    model_config = ConfigDict(frozen=True, extra="forbid")

    view_url: str | None = Field(
        description="Authenticated browser navigation URL for the Umbod file view, not a public share or download URL or an MCP resource URI; null when can_discover is false.",
    )


class FilesystemNodeSummary(FilesystemViewNodeSummary):
    model_config = ConfigDict(frozen=True, extra="forbid")

    sharing: SharingMetadata


class FilesystemNodeMetadata(NodeMetadata):
    model_config = ConfigDict(frozen=True, extra="forbid")


class FilesystemChildren(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    nodes: list[FilesystemNodeSummary]
