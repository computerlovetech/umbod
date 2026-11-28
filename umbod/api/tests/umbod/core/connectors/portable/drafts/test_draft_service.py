from asyncio import gather
from hashlib import sha256
from uuid import uuid4

import pytest

from umbod.core.callers import AuthenticationProvenance, CallerContext, DeclaredIssuer, SubjectIdentity, UnavailableSubject
from umbod.core.connectors.portable.drafts import (
    MAX_DRAFT_SOURCE_BYTES,
    DraftAuthorRequired,
    DraftHeadChanged,
    DraftReceipt,
    DraftRevisionNotFound,
    InvalidDraftSource,
    PortableConnectorDrafts,
)

pytestmark = pytest.mark.asyncio


def _caller(issuer: str, subject: str) -> CallerContext:
    return CallerContext(
        authentication=AuthenticationProvenance.UPSTREAM_VERIFIED,
        subject=SubjectIdentity(issuer=DeclaredIssuer(value=issuer), subject=subject),
    )


_AUTHOR = _caller("https://accounts.example", "author")
_OTHER_SUBJECT = _caller("https://accounts.example", "other")
_OTHER_ISSUER = _caller("https://different.example", "author")
_UNAUTHENTICATED = CallerContext(
    authentication=AuthenticationProvenance.UNAVAILABLE,
    subject=UnavailableSubject(kind="unavailable"),
)


async def test_create_preserves_exact_source_even_when_not_valid_python(drafts: PortableConnectorDrafts) -> None:
    source = "  import ???\r\n# æ\r\n"
    receipt = await drafts.create(_AUTHOR, source)

    revision = await drafts.read_revision(_AUTHOR, receipt.draft_id, receipt.revision_id)

    assert revision.source == source
    assert revision.receipt == receipt
    assert receipt.source_sha256 == sha256(source.encode("utf-8")).hexdigest()


async def test_source_at_utf8_byte_limit_is_accepted(drafts: PortableConnectorDrafts) -> None:
    source = "é" * (MAX_DRAFT_SOURCE_BYTES // 2)
    receipt = await drafts.create(_AUTHOR, source)

    assert (await drafts.read_revision(_AUTHOR, receipt.draft_id, receipt.revision_id)).source == source


@pytest.mark.parametrize("source", [" \n", "\ud800", "é" * (1 + MAX_DRAFT_SOURCE_BYTES // 2)], ids=["blank", "surrogate", "too-many-bytes"])
async def test_invalid_source_is_rejected(drafts: PortableConnectorDrafts, source: str) -> None:
    with pytest.raises(InvalidDraftSource):
        await drafts.create(_AUTHOR, source)


async def test_anonymous_caller_cannot_create_a_draft(drafts: PortableConnectorDrafts) -> None:
    with pytest.raises(DraftAuthorRequired):
        await drafts.create(_UNAUTHENTICATED, "source")


@pytest.mark.parametrize("other", [_OTHER_SUBJECT, _OTHER_ISSUER], ids=["different-subject", "different-issuer"])
async def test_other_author_cannot_read_or_append_and_gets_the_missing_result(
    drafts: PortableConnectorDrafts, other: CallerContext
) -> None:
    created = await drafts.create(_AUTHOR, "original")

    with pytest.raises(DraftRevisionNotFound, match="^Draft or revision not found$"):
        await drafts.read_revision(other, created.draft_id, created.revision_id)
    with pytest.raises(DraftRevisionNotFound, match="^Draft or revision not found$"):
        await drafts.save_revision(other, created.draft_id, created.revision_id, "replacement")
    with pytest.raises(DraftRevisionNotFound, match="^Draft or revision not found$"):
        await drafts.read_revision(_AUTHOR, uuid4(), created.revision_id)
    with pytest.raises(DraftRevisionNotFound, match="^Draft or revision not found$"):
        await drafts.save_revision(_AUTHOR, uuid4(), created.revision_id, "replacement")


async def test_revision_is_bound_to_its_draft(drafts: PortableConnectorDrafts) -> None:
    first = await drafts.create(_AUTHOR, "first")
    second = await drafts.create(_AUTHOR, "second")

    with pytest.raises(DraftRevisionNotFound):
        await drafts.read_revision(_AUTHOR, second.draft_id, first.revision_id)


async def test_save_appends_a_new_revision_and_preserves_the_previous_revision(drafts: PortableConnectorDrafts) -> None:
    first = await drafts.create(_AUTHOR, "first")
    second = await drafts.save_revision(_AUTHOR, first.draft_id, first.revision_id, "second")

    assert second.draft_id == first.draft_id
    assert second.revision_id != first.revision_id
    assert (await drafts.read_revision(_AUTHOR, first.draft_id, first.revision_id)).source == "first"
    assert (await drafts.read_revision(_AUTHOR, second.draft_id, second.revision_id)).source == "second"
    with pytest.raises(DraftHeadChanged):
        await drafts.save_revision(_AUTHOR, first.draft_id, first.revision_id, "stale")


async def test_two_writers_using_same_head_cannot_both_append(drafts: PortableConnectorDrafts) -> None:
    receipt = await drafts.create(_AUTHOR, "original")
    results = await gather(
        drafts.save_revision(_AUTHOR, receipt.draft_id, receipt.revision_id, "first"),
        drafts.save_revision(_AUTHOR, receipt.draft_id, receipt.revision_id, "second"),
        return_exceptions=True,
    )
    winners = [result for result in results if isinstance(result, DraftReceipt)]

    assert len(winners) == 1
    assert sum(isinstance(result, DraftHeadChanged) for result in results) == 1
    winner = await drafts.read_revision(_AUTHOR, receipt.draft_id, winners[0].revision_id)
    assert winner.source in {"first", "second"}
