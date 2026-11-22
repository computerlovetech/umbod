import pytest
from fastapi import HTTPException

from umbod.core.callers import (
    LOCAL_DEVELOPMENT_ISSUER,
    AuthenticationProvenance,
    CallerContext,
    DeclaredIssuer,
    SubjectIdentity,
)
from umbod.core.personal_access_tokens.ownership import (
    LocalDevelopmentPersonalAccessTokenOwnerResolver,
    VerifiedPersonalAccessTokenOwnerResolver,
)
from umbod.core.telemetry.analytics import OwnersScope, analytics_owner_id
from umbod.rest.telemetry_analytics.routes import get_personal_analytics_scope


def test_personal_scope_distinguishes_identical_subjects_from_different_issuers() -> None:
    resolver = VerifiedPersonalAccessTokenOwnerResolver()
    scopes = [get_personal_analytics_scope(
        CallerContext(
            authentication=AuthenticationProvenance.UPSTREAM_VERIFIED,
            subject=SubjectIdentity(issuer=DeclaredIssuer(value=issuer), subject="alice"),
        ),
        resolver,
    ) for issuer in ("https://a.example.test", "https://b.example.test")]
    assert len(scopes[0].owner_ids) == len(scopes[1].owner_ids) == 1
    assert scopes[0].owner_ids != scopes[1].owner_ids


def test_upstream_verified_caller_cannot_read_local_namespace_counts() -> None:
    caller = CallerContext(
        authentication=AuthenticationProvenance.UPSTREAM_VERIFIED,
        subject=SubjectIdentity(issuer=DeclaredIssuer(value=LOCAL_DEVELOPMENT_ISSUER), subject="alice"),
    )
    with pytest.raises(HTTPException) as forbidden:
        get_personal_analytics_scope(caller, VerifiedPersonalAccessTokenOwnerResolver())
    assert forbidden.value.status_code == 403


def test_simulated_caller_can_read_own_dev_pat_counts_under_local_policy() -> None:
    caller = CallerContext(
        authentication=AuthenticationProvenance.LOCAL_SIMULATION,
        subject=SubjectIdentity(issuer=DeclaredIssuer(value=LOCAL_DEVELOPMENT_ISSUER), subject="alice"),
    )
    assert get_personal_analytics_scope(caller, LocalDevelopmentPersonalAccessTokenOwnerResolver("alice")) == OwnersScope(
        kind="owners", owner_ids=(analytics_owner_id(LOCAL_DEVELOPMENT_ISSUER, "alice"),),
    )
