import hashlib

import pytest
from umbod.hosting import TokenVerifier

from umbod_desktop.backend_integration.authentication import DesktopAgentVerifier
from umbod_desktop.backward_compatibility.authentication import LegacyAgentCredentials


@pytest.mark.parametrize("token", ["", "unrecognized", "historical-token"])
async def test_agent_verifier_rejects_noncurrent_credentials_by_default(token: str) -> None:
    verifier: TokenVerifier = DesktopAgentVerifier("current-token")
    assert await verifier.verify_token(token) is None


async def test_agent_verifier_accepts_current_token_with_owner_group() -> None:
    verifier: TokenVerifier = DesktopAgentVerifier("current-token")
    result = await verifier.verify_token("current-token")
    assert result is not None
    assert result.claims == {"sub": "desktop-owner", "groups": ["desktop-owner"]}


async def test_agent_verifier_accepts_only_injected_historical_credentials() -> None:
    historical = "historical-token"
    digest = hashlib.sha256(historical.encode()).hexdigest()
    verifier: TokenVerifier = DesktopAgentVerifier("current-token", LegacyAgentCredentials((digest,)))
    assert await verifier.verify_token(historical) is not None
    assert await verifier.verify_token("current-token") is not None
    assert await verifier.verify_token("unknown") is None
