from hashlib import sha256
from uuid import UUID, uuid4

from umbod.core.callers import AuthenticationProvenance, CallerContext, DeclaredIssuer, SubjectIdentity

from .errors import DraftAuthorRequired, InvalidDraftSource
from .models import DraftAuthor, DraftReceipt, DraftRevision
from .ports import DraftStore

MAX_DRAFT_SOURCE_BYTES = 64 * 1024


class PortableConnectorDrafts:
    def __init__(self, store: DraftStore) -> None:
        self._store = store

    async def create(self, caller: CallerContext, source: str) -> DraftReceipt:
        author = require_draft_author(caller)
        revision = _new_revision(uuid4(), source)
        await self._store.create(author, revision)
        return revision.receipt

    async def save_revision(
        self, caller: CallerContext, draft_id: UUID, expected_revision_id: UUID, source: str
    ) -> DraftReceipt:
        author = require_draft_author(caller)
        revision = _new_revision(draft_id, source)
        await self._store.append(author, expected_revision_id, revision)
        return revision.receipt

    async def read_revision(self, caller: CallerContext, draft_id: UUID, revision_id: UUID) -> DraftRevision:
        return await self._store.read(require_draft_author(caller), draft_id, revision_id)


def require_draft_author(caller: CallerContext) -> DraftAuthor:
    subject = caller.subject
    if (
        caller.authentication not in (
            AuthenticationProvenance.UPSTREAM_VERIFIED,
            AuthenticationProvenance.DEPLOYMENT_AUTHENTICATED,
        )
        or not isinstance(subject, SubjectIdentity)
        or not isinstance(subject.issuer, DeclaredIssuer)
        or not subject.issuer.value.strip()
        or not subject.subject.strip()
    ):
        raise DraftAuthorRequired("An authenticated author is required")
    return DraftAuthor(issuer=subject.issuer.value, subject=subject.subject)


def _new_revision(draft_id: UUID, source: str) -> DraftRevision:
    if len(source) > MAX_DRAFT_SOURCE_BYTES or not source.strip():
        raise InvalidDraftSource("Provide nonblank connector source of at most 64 KiB in UTF-8")
    try:
        encoded = source.encode("utf-8")
    except UnicodeEncodeError:
        raise InvalidDraftSource("Connector source must be valid UTF-8") from None
    if len(encoded) > MAX_DRAFT_SOURCE_BYTES:
        raise InvalidDraftSource("Connector source exceeds 64 KiB in UTF-8")
    return DraftRevision(
        receipt=DraftReceipt(draft_id=draft_id, revision_id=uuid4(), source_sha256=sha256(encoded).hexdigest()),
        source=source,
    )
