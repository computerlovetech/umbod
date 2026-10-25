from types import SimpleNamespace

import pytest

from umbod.core.callers import AuthenticationProvenance, SubjectIdentity, UnavailableSubject
from umbod.mcp.auth.caller import caller_context_from_access_token


def test_caller_capture_retains_one_token_observation_after_source_changes() -> None:
    claims: dict[str, object] = {"sub": "first", "iss": "issuer", "groups": ["private"]}
    captured = caller_context_from_access_token(
        SimpleNamespace(claims=claims), AuthenticationProvenance.DEPLOYMENT_AUTHENTICATED,
    )
    claims.update(sub="second", iss="other")
    assert isinstance(captured.subject, SubjectIdentity)
    assert captured.subject.subject == "first"
    assert captured.subject.issuer.value == "issuer"
    assert set(captured.model_dump()) == {"authentication", "subject"}


@pytest.mark.parametrize("subject", ["", "  ", "person"])
def test_caller_capture_preserves_subject_strings_exactly(subject: str) -> None:
    captured = caller_context_from_access_token(
        SimpleNamespace(claims={"sub": subject}), AuthenticationProvenance.LOCAL_TEST,
    )
    assert isinstance(captured.subject, SubjectIdentity)
    assert captured.subject.subject == subject
    assert captured.authentication == AuthenticationProvenance.LOCAL_TEST


@pytest.mark.parametrize("claims", [{"sub": 17}, {}, {"sub": None}, []])
def test_caller_capture_models_unavailable_subject_without_rejecting_authentication(claims: object) -> None:
    captured = caller_context_from_access_token(
        SimpleNamespace(claims=claims), AuthenticationProvenance.DEPLOYMENT_AUTHENTICATED,
    )
    assert isinstance(captured.subject, UnavailableSubject)
    assert captured.authentication == AuthenticationProvenance.DEPLOYMENT_AUTHENTICATED


def test_caller_capture_cannot_establish_authentication_without_a_token() -> None:
    captured = caller_context_from_access_token(None, AuthenticationProvenance.UPSTREAM_VERIFIED)
    assert captured.authentication == AuthenticationProvenance.UNAVAILABLE
    assert isinstance(captured.subject, UnavailableSubject)
