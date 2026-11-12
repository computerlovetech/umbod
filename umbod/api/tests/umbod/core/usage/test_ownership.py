import pytest

from umbod.core.callers import (
    LOCAL_DEVELOPMENT_ISSUER,
    AuthenticationProvenance,
    CallerContext,
    DeclaredIssuer,
    SubjectIdentity,
    UnavailableIssuer,
    UnavailableSubject,
)
from umbod.core.usage import UnavailableUsageOwner, UsageOwner, resolve_usage_owner


def caller(issuer: str, subject: str, authentication: AuthenticationProvenance) -> CallerContext:
    return CallerContext(
        authentication=authentication,
        subject=SubjectIdentity(issuer=DeclaredIssuer(value=issuer), subject=subject),
    )


def test_verified_issuer_and_subject_produce_stable_opaque_ownership() -> None:
    identity = caller('https://issuer.example', 'private-subject', AuthenticationProvenance.UPSTREAM_VERIFIED)

    first = resolve_usage_owner(identity)
    second = resolve_usage_owner(identity)

    assert isinstance(first, UsageOwner)
    assert first == second
    assert len(first.owner_id) == 64
    assert 'private-subject' not in first.model_dump_json()
    assert 'issuer.example' not in first.model_dump_json()


def test_equal_subjects_at_distinct_issuers_do_not_share_usage() -> None:
    first = resolve_usage_owner(caller('https://one.example', 'same', AuthenticationProvenance.UPSTREAM_VERIFIED))
    second = resolve_usage_owner(caller('https://two.example', 'same', AuthenticationProvenance.UPSTREAM_VERIFIED))

    assert first != second
    assert isinstance(first, UsageOwner)
    assert isinstance(second, UsageOwner)


@pytest.mark.parametrize('issuer', ['https://issuer.example', 'https://issuer.example/'])
def test_owner_mapping_preserves_exact_verified_issuer_and_subject(issuer: str) -> None:
    original = resolve_usage_owner(caller(issuer, 'subject', AuthenticationProvenance.UPSTREAM_VERIFIED))
    changed = resolve_usage_owner(caller(issuer, ' subject ', AuthenticationProvenance.UPSTREAM_VERIFIED))

    assert original != changed


@pytest.mark.parametrize('provenance', [
    AuthenticationProvenance.DEPLOYMENT_AUTHENTICATED,
    AuthenticationProvenance.LOCAL_SEMANTIC,
    AuthenticationProvenance.LOCAL_TEST,
])
def test_unverified_or_deployment_identity_does_not_establish_usage_owner(provenance: AuthenticationProvenance) -> None:
    assert isinstance(resolve_usage_owner(caller('https://issuer.example', 'user', provenance)), UnavailableUsageOwner)


def test_only_reserved_local_issuer_can_establish_simulated_ownership() -> None:
    accepted = resolve_usage_owner(caller(LOCAL_DEVELOPMENT_ISSUER, 'user', AuthenticationProvenance.LOCAL_SIMULATION))
    rejected = resolve_usage_owner(caller('https://claimed.example', 'user', AuthenticationProvenance.LOCAL_SIMULATION))

    assert isinstance(accepted, UsageOwner)
    assert isinstance(rejected, UnavailableUsageOwner)


@pytest.mark.parametrize(('issuer', 'subject'), [('', 'user'), (' ', 'user'), ('issuer', ''), ('issuer', ' ')])
def test_incomplete_verified_identity_is_not_attributed(issuer: str, subject: str) -> None:
    assert isinstance(resolve_usage_owner(caller(issuer, subject, AuthenticationProvenance.UPSTREAM_VERIFIED)), UnavailableUsageOwner)


def test_unavailable_subject_or_issuer_does_not_establish_owner() -> None:
    missing_subject = CallerContext(authentication=AuthenticationProvenance.UNAVAILABLE, subject=UnavailableSubject(kind='unavailable'))
    missing_issuer = CallerContext(
        authentication=AuthenticationProvenance.UPSTREAM_VERIFIED,
        subject=SubjectIdentity(issuer=UnavailableIssuer(kind='unavailable'), subject='user'),
    )

    assert isinstance(resolve_usage_owner(missing_subject), UnavailableUsageOwner)
    assert isinstance(resolve_usage_owner(missing_issuer), UnavailableUsageOwner)
