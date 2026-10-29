from datetime import datetime
from typing import Union

from pydantic import BaseModel, ConfigDict, Field

from ..models import NodeId, NodeKind, NodeMetadata, RootParent


class BreadcrumbItem(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: NodeId
    name: str
    kind: NodeKind


class Breadcrumbs(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    items: list[BreadcrumbItem] = Field(min_length=1)
    complete: bool


class NodeSummary(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: NodeId
    parent_id: Union[NodeId, RootParent]
    name: str
    kind: NodeKind
    metadata: NodeMetadata
    created_at: datetime
    updated_at: datetime
    revision: int = Field(ge=1)
