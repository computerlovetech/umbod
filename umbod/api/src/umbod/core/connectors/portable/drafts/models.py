from dataclasses import dataclass, field
from uuid import UUID


@dataclass(frozen=True, slots=True)
class DraftAuthor:
    issuer: str = field(repr=False)
    subject: str = field(repr=False)


@dataclass(frozen=True, slots=True)
class DraftReceipt:
    draft_id: UUID
    revision_id: UUID
    source_sha256: str


@dataclass(frozen=True, slots=True)
class DraftRevision:
    receipt: DraftReceipt
    source: str = field(repr=False)
