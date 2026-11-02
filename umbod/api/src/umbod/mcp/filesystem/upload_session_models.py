from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from .models import FilesystemNodeMetadata, FilesystemNodeSummary


class BeginUploadCommand(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    parent_id: UUID
    name: str
    metadata: FilesystemNodeMetadata
    size_bytes: int = Field(
        ge=0, strict=True,
        description="Exact local file byte count, computed programmatically before beginning the upload.",
    )
    expected_sha256: str = Field(
        default="", pattern=r"^(?:[0-9a-f]{64})?$",
        description="Optional lowercase SHA256 computed programmatically from the local file; omitted or empty skips the check. Never guess the hash.",
    )


class CompleteUploadCommand(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    upload_id: UUID


class CapabilityTransfer(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    type: Literal["single"] = "single"
    method: Literal["PUT"] = "PUT"
    url: str
    headers: dict[str, str] = Field(repr=False)
    instructions: str = "Send raw bytes with only these required headers. Do not follow redirects. Do not send MCP bearer credentials or cookies."


class BeginUploadResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    upload_id: UUID
    expires_at: datetime = Field(description="Capability transfer deadline; completion uses the separate upload session lifetime.")
    transfer: CapabilityTransfer
    complete_tool: Literal["filesystem_complete_upload"] = "filesystem_complete_upload"


class CompleteUploadResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    node: FilesystemNodeSummary
    size_bytes: int = Field(ge=0)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
