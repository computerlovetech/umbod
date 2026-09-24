from collections.abc import Mapping, Sequence
from importlib import import_module
from typing import Any

from fastmcp.prompts import Prompt
from fastmcp.resources import Resource
from fastmcp.server.auth.auth import AccessToken
from fastmcp.server.auth import AuthContext
from fastmcp.tools import FunctionTool

import pytest



def test_connector_tool_change_is_prevented_when_it_would_break_existing_mapping() -> None:
    permissions = _new_permissions(group_claim_fields=["groups"])
    permissions.grant_tool("engineering", "github", "old_tool")

    with pytest.raises(ValueError, match="existing permission mapping"):
        permissions.validate_connector_tool_change(
            connector_id="github",
            previous_tool_names={"old_tool"},
            next_tool_names=set(),
        )


def test_connector_tool_auth_check_allows_granted_group_tool() -> None:
    permissions = _new_permissions(group_claim_fields=["groups"])
    permissions.grant_tool("engineering", "github", "list_repositories")
    check = _connector_tool_permission_check(permissions)

    assert (
        check(
            _auth_context(
                _connector_tool("github", "list_repositories"), {"groups": ["engineering"]}
            )
        )
        is True
    )


def test_connector_tool_auth_check_denies_enabled_tool_without_group_permission() -> None:
    permissions = _new_permissions(group_claim_fields=["groups"])
    permissions.grant_tool("support", "github", "list_repositories")
    check = _connector_tool_permission_check(permissions)

    assert (
        check(
            _auth_context(
                _connector_tool("github", "list_repositories"), {"groups": ["engineering"]}
            )
        )
        is False
    )
    assert check(_auth_context(_connector_tool("github", "list_repositories"), {})) is False


def test_connector_capability_auth_check_allows_granted_prompt_and_resource() -> None:
    permissions = _new_permissions(group_claim_fields=["groups"])
    permissions.grant_capability("engineering", "github", "prompt", "triage")
    permissions.grant_capability("engineering", "github", "resource", "docs://readme")
    check = _connector_capability_permission_check(permissions)

    assert check(_auth_context(_connector_prompt("github", "triage"), {"groups": ["engineering"]})) is True
    assert (
        check(_auth_context(_connector_resource("github", "docs://readme"), {"groups": ["engineering"]}))
        is True
    )
    assert check(_auth_context(_connector_prompt("github", "triage"), {"groups": ["support"]})) is False


def test_group_lifecycle_is_external_to_permission_management() -> None:
    permissions = _new_permissions(group_claim_fields=["groups"])

    assert hasattr(permissions, "grant_tool")
    assert not hasattr(permissions, "create_group")
    assert not hasattr(permissions, "rename_group")
    assert not hasattr(permissions, "delete_group")


def _new_permissions(group_claim_fields: Sequence[str]) -> Any:
    module = import_module("umbod.core.permissions")
    return module.InMemoryGroupConnectorToolPermissions(group_claim_fields=group_claim_fields)


def _connector_tool_permission_check(permissions: Any) -> Any:
    module = import_module("umbod.core.permissions")
    return module.connector_tool_permission_check(permissions)


def _connector_capability_permission_check(permissions: Any) -> Any:
    module = import_module("umbod.core.permissions")
    return module.connector_capability_permission_check(permissions)


def _connector_tool(connector_id: str, operation_name: str) -> FunctionTool:
    def operation() -> dict[str, str]:
        return {"status": "ok"}

    return FunctionTool.from_function(
        operation,
        name=f"{connector_id}_{operation_name}",
        meta={"connector_id": connector_id, "operation_name": operation_name},
    )


def _connector_prompt(connector_id: str, prompt_name: str) -> Prompt:
    async def render() -> str:
        return "ok"

    return Prompt.from_function(
        render,
        name=prompt_name,
        meta={
            "connector_id": connector_id,
            "capability_kind": "prompt",
            "capability_key": prompt_name,
        },
    )


def _connector_resource(connector_id: str, uri: str) -> Resource:
    async def read() -> str:
        return "ok"

    return Resource.from_function(
        read,
        uri=uri,
        name=uri,
        meta={
            "connector_id": connector_id,
            "capability_kind": "resource",
            "capability_key": uri,
        },
    )


def _auth_context(component: Any, claims: Mapping[str, object]) -> AuthContext:
    return AuthContext(
        token=AccessToken(
            token="test-token", client_id="test-client", scopes=[], claims=dict(claims)
        ),
        component=component,
    )
