import pytest
from fastmcp.server.auth import AccessToken

from umbod.core.callers import AuthenticationProvenance, CallerContextProvider
from umbod.mcp.connectors.openapi import principal as principal_module
from umbod.mcp.connectors.openapi.ports import CurrentPrincipal
from umbod.mcp.connectors.openapi.principal import JwtCurrentPrincipalGroups
from umbod.rest.authentication.authorization import JwtClaims
from umbod.rest.authentication.caller import RestCallerContextProvider


@pytest.mark.parametrize("subject,expected", [
    ("alice", "alice"), (" Alice ", " Alice "), ("", "authenticated-principal"),
    (None, "authenticated-principal"), (42, "authenticated-principal"),
])
def test_openapi_subject_projection_preserves_legacy_fallback(subject: object, expected: str) -> None:
    callers: CallerContextProvider = RestCallerContextProvider(
        JwtClaims(claims={"sub": subject}), AuthenticationProvenance.DEPLOYMENT_AUTHENTICATED,
    )
    principal: CurrentPrincipal = JwtCurrentPrincipalGroups("groups", callers)
    assert principal.subject() == expected


@pytest.mark.parametrize("groups,expected", [
    ([" team ", "", 1, "alpha", "alpha"], (" team ", "alpha")),
    (" ", (" ",)), ({"alpha": True}, ()), (None, ()),
])
def test_openapi_group_projection_is_not_replaced_by_personal_group_normalization(
    monkeypatch: pytest.MonkeyPatch, groups: object, expected: tuple[str, ...],
) -> None:
    callers: CallerContextProvider = RestCallerContextProvider(
        JwtClaims(claims={"sub": "alice"}), AuthenticationProvenance.DEPLOYMENT_AUTHENTICATED,
    )
    monkeypatch.setattr(principal_module, "get_access_token", lambda: AccessToken(
        token="secret", client_id="client", scopes=[], claims={"groups": groups},
    ))
    principal: CurrentPrincipal = JwtCurrentPrincipalGroups("groups", callers)
    assert principal.groups() == expected
