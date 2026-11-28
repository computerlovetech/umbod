from fastmcp.server.auth import AuthContext
from fastmcp.server.auth.auth import AccessToken
from fastmcp.tools import FunctionTool
import pytest

from umbod.core.callers import AuthenticationProvenance
from umbod.core.callers.membership import (
    INHERITED_GROUP_MEMBERSHIP,
    GroupMembershipResolver,
    ProviderGroupOverrides,
    ProviderMembershipClaim,
)
from umbod.core.permissions import InMemoryGroupConnectorToolPermissions
from umbod.mcp.authorization import connector_tool_permission_check


def _sdk_context(claims: object, tagged: bool) -> AuthContext:
    def operation() -> str:
        return "ok"

    tool = FunctionTool.from_function(
        operation,
        meta={"connector_id": "github", "operation_name": "issues"} if tagged else {},
    )
    token = AccessToken(token="test", client_id="test", scopes=[], claims={})
    token = token.model_copy(update={"claims": claims})
    return AuthContext(token=token, component=tool)


@pytest.mark.parametrize("value,allowed", [
    ("", True),
    ("  ", True),
    (["team", 42, None], True),
    ({"team": False}, True),
    ({"team"}, True),
    (iter(["team", 42]), True),
    (42, False),
    (None, False),
    ([42, ["team"]], False),
])
def test_sdk_permission_callback_uses_runtime_literal_capture(value: object, allowed: bool) -> None:
    permissions = InMemoryGroupConnectorToolPermissions(group_claim_fields=("groups", "roles"))
    for group in ("", "  ", "team"):
        permissions.grant_tool(group, "github", "issues")
    check = connector_tool_permission_check(permissions, INHERITED_GROUP_MEMBERSHIP, AuthenticationProvenance.DEPLOYMENT_AUTHENTICATED)
    assert check(_sdk_context({"roles": value}, True)) is allowed


@pytest.mark.parametrize("claims", [None, "team", ["team"], 42])
def test_sdk_permission_callback_denies_malformed_claims_but_allows_untagged_components(claims: object) -> None:
    permissions = InMemoryGroupConnectorToolPermissions(group_claim_fields=("groups",))
    check = connector_tool_permission_check(permissions, INHERITED_GROUP_MEMBERSHIP, AuthenticationProvenance.DEPLOYMENT_AUTHENTICATED)
    assert check(_sdk_context(claims, True)) is False
    assert check(_sdk_context(claims, False)) is True


def test_sdk_permission_callback_reads_current_grants_and_token_each_call() -> None:
    permissions = InMemoryGroupConnectorToolPermissions(group_claim_fields=("groups",))
    permissions.grant_tool("team", "github", "issues")
    check = connector_tool_permission_check(permissions, INHERITED_GROUP_MEMBERSHIP, AuthenticationProvenance.DEPLOYMENT_AUTHENTICATED)
    assert check(_sdk_context({"groups": "team"}, True)) is True
    assert check(_sdk_context({"groups": "other"}, True)) is False
    permissions.replace_group_permissions({}, {})
    assert check(_sdk_context({"groups": "team"}, True)) is False


@pytest.mark.parametrize(
    "claims,mapped_allowed,legacy_allowed",
    [
        ({"groups": ["external-team"]}, True, False),
        ({"provider_roles": ["external-team"]}, False, False),
        ({"provider_roles": ["registered-team"]}, False, True),
        ({"groups": ["registered-team"]}, False, True),
        ({"groups": ["independent-team"]}, False, True),
    ],
)
def test_sdk_permission_callback_uses_configured_group_policy(
    claims: dict[str, object], mapped_allowed: bool, legacy_allowed: bool,
) -> None:
    issuer = "https://issuer.example/"
    permissions = InMemoryGroupConnectorToolPermissions(group_claim_fields=("groups", "provider_roles"))
    permissions.grant_tool("registered-team", "github", "issues")
    permissions.grant_tool("independent-team", "github", "issues")
    resolver = GroupMembershipResolver(ProviderGroupOverrides(
        ProviderMembershipClaim(issuer, "groups"),
        {"external-team": ("registered-team",), "registered-team": ()},
    ))
    context = _sdk_context({"iss": issuer, "sub": "member", **claims}, True)

    mapped_check = connector_tool_permission_check(
        permissions, resolver, AuthenticationProvenance.UPSTREAM_VERIFIED,
    )
    legacy_check = connector_tool_permission_check(permissions, INHERITED_GROUP_MEMBERSHIP, AuthenticationProvenance.DEPLOYMENT_AUTHENTICATED)

    assert mapped_check(context) is mapped_allowed
    assert legacy_check(context) is legacy_allowed
