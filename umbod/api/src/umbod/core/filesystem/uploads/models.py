from datetime import datetime
from typing import Annotated, Literal, Union
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from ..browsing import NodeSummary
from ..models import ContentRef, NodeId, NodeMetadata, Principal


class PendingUpload(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: Literal["pending"] = "pending"


class UploadedContent(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: Literal["uploaded"] = "uploaded"
    content: ContentRef


class CompletedUpload(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: Literal["completed"] = "completed"
    node: NodeSummary


class UploadSession(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: UUID
    owner: Principal
    parent_id: NodeId
    name: str
    metadata: NodeMetadata
    size_bytes: int = Field(ge=0, strict=True)
    expires_at: datetime
    progress: Annotated[Union[PendingUpload, UploadedContent, CompletedUpload], Field(discriminator="status")]


class UploadCompletion(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    node: NodeSummary
    created: bool
