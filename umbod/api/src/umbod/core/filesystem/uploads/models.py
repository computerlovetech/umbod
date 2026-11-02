from datetime import datetime
from typing import Annotated, Literal, Union
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from ..authorization.models import ResolvedIdentity
from ..browsing import NodeSummary
from ..models import ContentRef, NodeId, NodeMetadata, Principal


class UnavailableReceipt(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["unavailable"] = "unavailable"


class VerifiedReceipt(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["verified"] = "verified"
    size_bytes: int = Field(ge=0, strict=True)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


UploadReceipt = Annotated[Union[UnavailableReceipt, VerifiedReceipt], Field(discriminator="kind")]


class NoExpectedChecksum(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["unchecked"] = "unchecked"


class ExpectedChecksum(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["sha256"] = "sha256"
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


ChecksumExpectation = Annotated[Union[NoExpectedChecksum, ExpectedChecksum], Field(discriminator="kind")]


class NoDelegatedTransfer(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["none"] = "none"


class AvailableTransfer(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: Literal["available"] = "available"


class ClaimedTransfer(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: Literal["claimed"] = "claimed"
    claim_id: UUID


class ConsumedTransfer(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: Literal["consumed"] = "consumed"


class DelegatedTransfer(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["delegated"] = "delegated"
    token_digest: str = Field(pattern=r"^[0-9a-f]{64}$", repr=False)
    identity: ResolvedIdentity
    expires_at: datetime
    state: Annotated[Union[AvailableTransfer, ClaimedTransfer, ConsumedTransfer], Field(discriminator="status")]


TransferGrant = Annotated[Union[NoDelegatedTransfer, DelegatedTransfer], Field(discriminator="kind")]


class PendingUpload(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: Literal["pending"] = "pending"


class UploadedContent(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: Literal["uploaded"] = "uploaded"
    content: ContentRef
    receipt: UploadReceipt = Field(default_factory=UnavailableReceipt)


class CompletedUpload(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: Literal["completed"] = "completed"
    node: NodeSummary
    receipt: UploadReceipt = Field(default_factory=UnavailableReceipt)


class UploadSession(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: UUID
    owner: Principal
    parent_id: NodeId
    name: str
    metadata: NodeMetadata
    size_bytes: int = Field(ge=0, strict=True)
    expires_at: datetime
    expected_checksum: ChecksumExpectation = Field(default_factory=NoExpectedChecksum)
    delegated_transfer: TransferGrant = Field(default_factory=NoDelegatedTransfer)
    progress: Annotated[Union[PendingUpload, UploadedContent, CompletedUpload], Field(discriminator="status")]


class UploadCompletion(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    node: NodeSummary
    created: bool
    receipt: UploadReceipt = Field(default_factory=UnavailableReceipt)


class DelegatedUpload(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    session: UploadSession
    expires_at: datetime
    token: str = Field(repr=False, exclude=True)
