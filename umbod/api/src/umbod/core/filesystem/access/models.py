from typing import Annotated, Literal, Union
from uuid import UUID

from pydantic import ConfigDict, Field

from umbod.proxies import Model

from ..browsing import NodeSummary


class CallerPermissions(Model):
    model_config = ConfigDict(frozen=True, extra="forbid")

    can_discover: bool
    can_read: bool
    can_write: bool
    can_delete: bool
    can_share: bool


class NamespaceVisibility(Model):
    model_config = ConfigDict(frozen=True, extra="forbid")

    type: Literal["namespace"]
    namespace_id: UUID
    kind: Literal["personal", "shared"]
    name: str


class RestrictedVisibility(Model):
    model_config = ConfigDict(frozen=True, extra="forbid")

    type: Literal["restricted"]


Visibility = Annotated[
    Union[NamespaceVisibility, RestrictedVisibility], Field(discriminator="type"),
]


class CallerNodeSummary(NodeSummary):
    permissions: CallerPermissions
    visible_to: Visibility = Field(description="Namespace location metadata, not the complete audience; individual item sharing can grant additional access.")
