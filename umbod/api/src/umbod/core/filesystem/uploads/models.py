from datetime import datetime
from typing import Annotated, Literal, Union
from uuid import UUID

from pydantic import ConfigDict, Field

from umbod.proxies import Model

from ..authorization.models import ResolvedIdentity
from ..browsing import NodeSummary
from ..models import ContentRef, NodeId, NodeMetadata, Principal


class UnavailableReceipt(Model):
    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["unavailable"] = "unavailable"


class VerifiedReceipt(Model):
    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["verified"] = "verified"
    size_bytes: int = Field(ge=0, strict=True)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


UploadReceipt = Annotated[Union[UnavailableReceipt, VerifiedReceipt], Field(discriminator="kind")]


class NoExpectedChecksum(Model):
    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["unchecked"] = "unchecked"


class ExpectedChecksum(Model):
    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["sha256"] = "sha256"
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


ChecksumExpectation = Annotated[Union[NoExpectedChecksum, ExpectedChecksum], Field(discriminator="kind")]


class NoDelegatedTransfer(Model):
    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["none"] = "none"


class AvailableTransfer(Model):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: Literal["available"] = "available"


class ClaimedTransfer(Model):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: Literal["claimed"] = "claimed"
    claim_id: UUID


class ConsumedTransfer(Model):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: Literal["consumed"] = "consumed"


class DelegatedTransfer(Model):
    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["delegated"] = "delegated"
    token_digest: str = Field(pattern=r"^[0-9a-f]{64}$", repr=False)
    identity: ResolvedIdentity
    expires_at: datetime
    state: Annotated[Union[AvailableTransfer, ClaimedTransfer, ConsumedTransfer], Field(discriminator="status")]


class ExternalTransfer(Model):
    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["external"] = "external"
    storage_key: str = Field(pattern=r"^[0-9a-f]{32}$")
    expires_at: datetime


class ExternalTransferRequest(Model):
    model_config = ConfigDict(frozen=True, extra="forbid")

    transfer: ExternalTransfer
    size_bytes: int = Field(ge=0, strict=True)
    content_type: str


class ExternalTransferInstructions(Model):
    model_config = ConfigDict(frozen=True, extra="forbid")

    url: str = Field(repr=False)
    headers: dict[str, str] = Field(repr=False)


class UnavailableExternalTransfer(Model):
    model_config = ConfigDict(frozen=True, extra="forbid")

    reason: Literal["expired", "completed"]


TransferGrant = Annotated[Union[NoDelegatedTransfer, DelegatedTransfer, ExternalTransfer], Field(discriminator="kind")]


class PendingUpload(Model):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: Literal["pending"] = "pending"


class UploadedContent(Model):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: Literal["uploaded"] = "uploaded"
    content: ContentRef
    receipt: UploadReceipt = Field(default_factory=UnavailableReceipt)


class CompletedUpload(Model):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: Literal["completed"] = "completed"
    node: NodeSummary
    receipt: UploadReceipt = Field(default_factory=UnavailableReceipt)


class UploadSession(Model):
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


class UploadCompletion(Model):
    model_config = ConfigDict(frozen=True, extra="forbid")

    node: NodeSummary
    created: bool
    receipt: UploadReceipt = Field(default_factory=UnavailableReceipt)


class DelegatedUpload(Model):
    model_config = ConfigDict(frozen=True, extra="forbid")

    session: UploadSession
    expires_at: datetime
    token: str = Field(repr=False, exclude=True)
