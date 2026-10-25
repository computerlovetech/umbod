import ast
import inspect
from pathlib import Path

import pytest
from pydantic import ValidationError

from umbod.core.callers import GroupMembership
from umbod.core.permissions import (
    ConnectorCapabilityPermission,
    ConnectorToolPermission,
    InMemoryGroupConnectorToolPermissions,
    RuntimeGroupPermissions,
)


def test_membership_is_required_frozen_and_retains_observed_ids() -> None:
    with pytest.raises(ValidationError):
        GroupMembership()
    membership = GroupMembership(group_ids=("", "  ", "team", "team"))
    assert membership.group_ids == ("", "  ", "team", "team")
    with pytest.raises(ValidationError):
        membership.group_ids = ()


def test_runtime_permission_protocol_evaluates_membership_not_adapter_metadata() -> None:
    state = InMemoryGroupConnectorToolPermissions(group_claim_fields=("unrelated",))
    state.grant_connector("team", "connector-only")
    state.grant_tool("team", "github", "issues")
    state.grant_capability("other", "docs", "resource", "docs://readme")
    permissions: RuntimeGroupPermissions = state
    groups = GroupMembership(group_ids=("team", "other", "team"))

    assert permissions.allowed_connector_ids(groups) == {"connector-only", "github", "docs"}
    assert permissions.allowed_tools(groups) == {ConnectorToolPermission("github", "issues")}
    assert permissions.allowed_capabilities(groups) == {
        ConnectorCapabilityPermission("github", "tool", "issues"),
        ConnectorCapabilityPermission("docs", "resource", "docs://readme"),
    }
    assert permissions.allowed_connector_ids(GroupMembership(group_ids=())) == set()
    state.replace_group_permissions({}, {})
    assert permissions.allowed_capabilities(groups) == set()


def test_hosting_runtime_reexport_identity_and_constructor_remain_compatible() -> None:
    from umbod.hosting import InMemoryGroupConnectorToolPermissions as HostedPermissions
    from umbod.hosting.contracts import InMemoryGroupConnectorToolPermissions as ContractPermissions

    assert HostedPermissions is ContractPermissions is InMemoryGroupConnectorToolPermissions
    parameter = inspect.signature(HostedPermissions).parameters["group_claim_fields"]
    assert parameter.kind == inspect.Parameter.KEYWORD_ONLY
    assert parameter.default is inspect.Parameter.empty
    assert HostedPermissions(group_claim_fields=["groups", "roles"]).group_claim_fields == ("groups", "roles")


def test_core_permission_evaluators_never_parse_claims() -> None:
    root = Path(__file__).parents[4] / "src" / "umbod" / "core" / "permissions"
    for path in root.rglob("*.py"):
        tree = ast.parse(path.read_text())
        assert not any(
            isinstance(node, ast.Name) and node.id in {"jwt_claims", "claims", "_groups_from_claims"}
            for node in ast.walk(tree)
        ), path
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name.startswith("_allowed_"):
                assert not any(isinstance(child, ast.Attribute) and child.attr == "group_claim_fields" for child in ast.walk(node))
