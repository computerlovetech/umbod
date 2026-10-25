import pytest
from pydantic import ValidationError

from umbod.core.callers import (
    AuthenticationProvenance,
    CallerContext,
    DeclaredIssuer,
    SubjectIdentity,
    UnavailableIssuer,
    UnavailableSubject,
)


def test_caller_observation_preserves_exact_subject_and_issuer() -> None:
    context = CallerContext(
        authentication=AuthenticationProvenance.UPSTREAM_VERIFIED,
        subject=SubjectIdentity(
            issuer=DeclaredIssuer(value="https://issuer.example/"), subject=" Alice "
        ),
    )
    assert context.subject == SubjectIdentity(
        issuer=DeclaredIssuer(value="https://issuer.example/"), subject=" Alice "
    )


def test_subject_identity_distinguishes_issuers() -> None:
    assert SubjectIdentity(
        issuer=DeclaredIssuer(value="https://one.example"), subject="alice"
    ) != SubjectIdentity(
        issuer=DeclaredIssuer(value="https://two.example"), subject="alice"
    )


@pytest.mark.parametrize("subject", ["", " ", "alice"])
def test_subject_observations_do_not_add_canonical_identity_requirements(subject: str) -> None:
    assert SubjectIdentity(
        issuer=UnavailableIssuer(kind="unavailable"), subject=subject
    ).subject == subject


@pytest.mark.parametrize("authentication", list(AuthenticationProvenance))
def test_authentication_can_have_an_unavailable_subject(authentication: AuthenticationProvenance) -> None:
    context = CallerContext(
        authentication=authentication, subject=UnavailableSubject(kind="unavailable")
    )
    assert isinstance(context.subject, UnavailableSubject)


def test_unavailable_authentication_cannot_claim_an_identified_subject() -> None:
    with pytest.raises(ValidationError):
        CallerContext(
            authentication=AuthenticationProvenance.UNAVAILABLE,
            subject=SubjectIdentity(issuer=UnavailableIssuer(kind="unavailable"), subject="alice"),
        )


def test_shared_caller_rejects_credentials_and_arbitrary_claims() -> None:
    with pytest.raises(ValidationError):
        CallerContext.model_validate({
            "authentication": "upstream_verified",
            "subject": {"issuer": {"kind": "unavailable"}, "subject": "alice"},
            "token": "secret",
        })


def test_caller_and_nested_identity_are_immutable() -> None:
    subject = SubjectIdentity(issuer=DeclaredIssuer(value="issuer"), subject="alice")
    context = CallerContext(authentication=AuthenticationProvenance.UPSTREAM_VERIFIED, subject=subject)
    with pytest.raises(ValidationError):
        context.authentication = AuthenticationProvenance.UNAVAILABLE
    with pytest.raises(ValidationError):
        subject.subject = "bob"
    with pytest.raises(ValidationError):
        subject.issuer.value = "different"


def test_shared_caller_fields_are_required() -> None:
    with pytest.raises(ValidationError):
        CallerContext.model_validate({})
    with pytest.raises(ValidationError):
        UnavailableSubject.model_validate({})
    with pytest.raises(ValidationError):
        UnavailableIssuer.model_validate({})
