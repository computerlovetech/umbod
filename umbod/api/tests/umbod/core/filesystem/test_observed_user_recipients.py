from datetime import datetime, timezone

import pytest

from tests.support.identity_directory import InMemoryIdentityDirectory
from umbod.core.callers import (
    AuthenticationProvenance,
    CallerContext,
    CallerSnapshot,
    DeclaredIssuer,
    GroupMembership,
    SubjectIdentity,
)
from umbod.core.filesystem.authorization import (
    ObservedUserPrincipalResolver,
    ResolvedIdentity,
    VerifiedIdentityResolver,
)
from umbod.core.filesystem.models import Principal, PrincipalType
from umbod.core.identity_directory.models import IdentityObservation
from umbod.core.identity_directory.user_models import UserSearchQuery
from umbod.core.identity_directory.users import (
    ObservedUserNotFound,
    ObservedUserService,
)


@pytest.mark.asyncio
async def test_selected_observed_user_resolves_to_existing_authorization_principal() -> (
    None
):
    directory = InMemoryIdentityDirectory()
    issuer = "https://issuer.test"
    await directory.observe(
        IdentityObservation(
            issuer=issuer,
            subject="recipient-subject",
            claim="groups",
            groups=(),
            name="Ada Lovelace",
            email="private@example.test",
            email_verification="verified",
            observed_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
    )
    users = ObservedUserService(directory, issuer)
    caller = CallerContext(
        authentication=AuthenticationProvenance.UPSTREAM_VERIFIED,
        subject=SubjectIdentity(issuer=DeclaredIssuer(value=issuer), subject="sharer"),
    )
    selected = (
        await users.search(caller, UserSearchQuery(query="Lovelace", limit=50, excluded_subjects=frozenset()))
    ).users[0]
    principal = await ObservedUserPrincipalResolver(users).resolve(
        caller, selected.user_id
    )
    recipient = CallerSnapshot(
        caller=CallerContext(
            authentication=AuthenticationProvenance.UPSTREAM_VERIFIED,
            subject=SubjectIdentity(
                issuer=DeclaredIssuer(value=issuer), subject="recipient-subject"
            ),
        ),
        groups=GroupMembership(group_ids=()),
    )
    identity = await VerifiedIdentityResolver().resolve(recipient)
    assert isinstance(identity, ResolvedIdentity)
    assert (
        principal
        == identity.user
        == Principal(type=PrincipalType.USER, issuer=issuer, id="recipient-subject")
    )
    assert principal.id != selected.user_id


@pytest.mark.asyncio
async def test_unknown_selected_user_does_not_produce_a_principal() -> None:
    issuer = "https://issuer.test"
    users = ObservedUserService(InMemoryIdentityDirectory(), issuer)
    caller = CallerContext(
        authentication=AuthenticationProvenance.UPSTREAM_VERIFIED,
        subject=SubjectIdentity(issuer=DeclaredIssuer(value=issuer), subject="sharer"),
    )
    with pytest.raises(ObservedUserNotFound):
        await ObservedUserPrincipalResolver(users).resolve(caller, "unknown")
