from dataclasses import dataclass

import pytest

from umbod.core.callers import AuthenticationProvenance
from umbod.core.usage.models import UnavailableUsageOwner, UsageOwner
from umbod.mcp.logging.audit.identity import McpAuditIdentityAdapter


@dataclass(frozen=True)
class AccessToken:
    claims: dict[str, str]
    client_id: str


@pytest.mark.parametrize('provenance,claims,owned', [
    (AuthenticationProvenance.UPSTREAM_VERIFIED, {'iss': 'https://verified', 'sub': 'subject'}, True),
    (AuthenticationProvenance.UPSTREAM_VERIFIED, {'sub': 'subject'}, False),
    (AuthenticationProvenance.DEPLOYMENT_AUTHENTICATED, {'iss': 'https://verified', 'sub': 'subject'}, False),
    (AuthenticationProvenance.LOCAL_TEST, {'iss': 'https://verified', 'sub': 'subject'}, False),
    (AuthenticationProvenance.UPSTREAM_VERIFIED, {'email': 'subject'}, False),
])
def test_invocation_actor_captures_only_trusted_opaque_usage_owner(
    monkeypatch: pytest.MonkeyPatch, provenance: AuthenticationProvenance,
    claims: dict[str, str], owned: bool,
) -> None:
    monkeypatch.setattr('umbod.mcp.logging.audit.identity.get_access_token', lambda: AccessToken(claims, 'client'))
    monkeypatch.setattr('umbod.mcp.logging.audit.identity.authentication_provenance', lambda provider: provenance)
    actor = McpAuditIdentityAdapter().invocation_actor(None)
    assert isinstance(actor.usage_owner, UsageOwner if owned else UnavailableUsageOwner)
    assert actor.authenticated_user_id == 'subject'
    assert actor.agent_client_id == 'client'
    assert 'https://verified' not in repr(actor.usage_owner)
    assert 'subject' not in repr(actor.usage_owner)
