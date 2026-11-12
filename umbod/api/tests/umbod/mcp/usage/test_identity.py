from types import SimpleNamespace

import pytest
from fastmcp.server.auth.providers.google import GoogleProvider

from umbod.core.callers import AuthenticationProvenance, CallerContext, DeclaredIssuer, SubjectIdentity, UnavailableIssuer
from umbod.core.usage import UnavailableUsageOwner, UsageOwner, resolve_usage_owner
from umbod.mcp.logging.audit import identity as audit_identity
from umbod.mcp.logging.audit.identity import McpAuditIdentityAdapter
from umbod.mcp.usage.identity import resolve_mcp_usage_owner


@pytest.fixture
def google_provider() -> GoogleProvider:
    return GoogleProvider(
        client_id='usage-test.apps.googleusercontent.com', client_secret='test-only-secret',
        base_url='https://umbod.example.test', jwt_signing_key='a' * 32,
    )


def google_caller(authentication: AuthenticationProvenance) -> CallerContext:
    return CallerContext(
        authentication=authentication,
        subject=SubjectIdentity(issuer=UnavailableIssuer(kind='unavailable'), subject='google-subject'),
    )


@pytest.mark.parametrize('issuer', ['https://accounts.google.com', 'accounts.google.com'])
def test_verified_google_tokeninfo_identity_matches_configured_rest_issuer(
    google_provider: GoogleProvider, issuer: str,
) -> None:
    mcp_owner = resolve_mcp_usage_owner(google_caller(AuthenticationProvenance.UPSTREAM_VERIFIED), google_provider, issuer)
    rest_owner = resolve_usage_owner(CallerContext(
        authentication=AuthenticationProvenance.UPSTREAM_VERIFIED,
        subject=SubjectIdentity(issuer=DeclaredIssuer(value=issuer), subject='google-subject'),
    ))

    assert isinstance(mcp_owner, UsageOwner)
    assert mcp_owner == rest_owner


@pytest.mark.parametrize('issuer', ['', 'https://other-issuer.test', ' https://accounts.google.com '])
def test_missing_google_issuer_is_not_filled_from_unapproved_configuration(
    google_provider: GoogleProvider, issuer: str,
) -> None:
    owner = resolve_mcp_usage_owner(google_caller(AuthenticationProvenance.UPSTREAM_VERIFIED), google_provider, issuer)

    assert isinstance(owner, UnavailableUsageOwner)


@pytest.mark.parametrize('authentication', [AuthenticationProvenance.LOCAL_TEST, AuthenticationProvenance.DEPLOYMENT_AUTHENTICATED])
def test_provider_shape_does_not_upgrade_unverified_caller_provenance(
    google_provider: GoogleProvider, authentication: AuthenticationProvenance,
) -> None:
    owner = resolve_mcp_usage_owner(google_caller(authentication), google_provider, 'https://accounts.google.com')

    assert isinstance(owner, UnavailableUsageOwner)


def test_unknown_provider_cannot_supply_missing_issuer() -> None:
    owner = resolve_mcp_usage_owner(
        google_caller(AuthenticationProvenance.UPSTREAM_VERIFIED), object(), 'https://accounts.google.com',
    )

    assert isinstance(owner, UnavailableUsageOwner)


def test_declared_verified_issuer_is_never_overwritten(google_provider: GoogleProvider) -> None:
    caller = CallerContext(
        authentication=AuthenticationProvenance.UPSTREAM_VERIFIED,
        subject=SubjectIdentity(issuer=DeclaredIssuer(value='https://existing-issuer.test'), subject='google-subject'),
    )

    assert resolve_mcp_usage_owner(caller, google_provider, 'https://accounts.google.com') == resolve_usage_owner(caller)


def test_audit_adapter_captures_opaque_usage_owner_without_changing_diagnostic_actor(
    google_provider: GoogleProvider, monkeypatch: pytest.MonkeyPatch,
) -> None:
    token = SimpleNamespace(claims={'sub': 'google-subject'}, client_id='google-client')
    monkeypatch.setattr(audit_identity, 'get_access_token', lambda: token)
    context = SimpleNamespace(fastmcp=SimpleNamespace(
        auth=google_provider, usage_identity_issuer='https://accounts.google.com',
    ))

    actor = McpAuditIdentityAdapter().invocation_actor(context)

    assert actor.authenticated_user_id == 'google-subject'
    assert isinstance(actor.usage_owner, UsageOwner)
    assert 'google-subject' not in actor.usage_owner.model_dump_json()
    assert actor.usage_owner == resolve_mcp_usage_owner(
        google_caller(AuthenticationProvenance.UPSTREAM_VERIFIED), google_provider, 'https://accounts.google.com',
    )
