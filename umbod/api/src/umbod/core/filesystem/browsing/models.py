from datetime import datetime
from typing import Union

from pydantic import ConfigDict, Field

from umbod.proxies import Model

from ..models import NodeId, NodeKind, NodeMetadata, RootParent


class BreadcrumbItem(Model):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: NodeId
    name: str
    kind: NodeKind


class Breadcrumbs(Model):
    model_config = ConfigDict(frozen=True, extra="forbid")

    items: list[BreadcrumbItem] = Field(min_length=1)
    complete: bool


class NodeSummary(Model):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: NodeId
    parent_id: Union[NodeId, RootParent]
    name: str
    kind: NodeKind
    metadata: NodeMetadata
    created_at: datetime
    updated_at: datetime
    revision: int = Field(ge=1)
