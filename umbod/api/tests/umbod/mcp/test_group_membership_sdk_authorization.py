from fastmcp.server.auth import AuthContext
from fastmcp.server.auth.auth import AccessToken
from fastmcp.tools import FunctionTool
import pytest

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
    check = connector_tool_permission_check(permissions)
    assert check(_sdk_context({"roles": value}, True)) is allowed


@pytest.mark.parametrize("claims", [None, "team", ["team"], 42])
def test_sdk_permission_callback_denies_malformed_claims_but_allows_untagged_components(claims: object) -> None:
    permissions = InMemoryGroupConnectorToolPermissions(group_claim_fields=("groups",))
    check = connector_tool_permission_check(permissions)
    assert check(_sdk_context(claims, True)) is False
    assert check(_sdk_context(claims, False)) is True


def test_sdk_permission_callback_reads_current_grants_and_token_each_call() -> None:
    permissions = InMemoryGroupConnectorToolPermissions(group_claim_fields=("groups",))
    permissions.grant_tool("team", "github", "issues")
    check = connector_tool_permission_check(permissions)
    assert check(_sdk_context({"groups": "team"}, True)) is True
    assert check(_sdk_context({"groups": "other"}, True)) is False
    permissions.replace_group_permissions({}, {})
    assert check(_sdk_context({"groups": "team"}, True)) is False
