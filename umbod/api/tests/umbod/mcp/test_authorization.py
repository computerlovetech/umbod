from types import SimpleNamespace
from typing import cast

import pytest
from fastmcp.server.auth import AccessToken, AuthContext
from fastmcp.utilities.components import FastMCPComponent

from umbod.core.capabilities.domain import CapabilityKind
from umbod.core.permissions import ConnectorCapabilityPermission, InMemoryGroupConnectorToolPermissions
from umbod.mcp.authorization import (
    connector_capability_permission_check,
    connector_tool_permission_check,
)


class MetadataOnlyComponent:
    def __init__(self, metadata: dict[str, object]) -> None:
        self.meta = metadata


@pytest.mark.parametrize("capability_kind", ["tool", "prompt", "resource", "resource_template"])
@pytest.mark.parametrize("metadata_api", ["get_meta", "meta"])
def test_component_grants_are_rechecked_after_permission_replacement(
    capability_kind: CapabilityKind, metadata_api: str
) -> None:
    permissions = InMemoryGroupConnectorToolPermissions(group_claim_fields=["groups"])
    metadata: dict[str, object] = {
        "connector_id": "connector",
        "capability_kind": capability_kind,
        "capability_key": "capability",
    }
    component = (
        FastMCPComponent(name="capability", meta=metadata)
        if metadata_api == "get_meta"
        else cast(FastMCPComponent, MetadataOnlyComponent(metadata))
    )
    context = AuthContext(
        token=AccessToken(
            token="token", client_id="client", scopes=[], claims={"groups": ["engineering"]}
        ),
        component=component,
    )
    check = connector_capability_permission_check(permissions)

    assert check(context) is False
    permissions.replace_group_permissions({}, {"engineering": [ConnectorCapabilityPermission(
        connector_id="connector", capability_kind=capability_kind, capability_key="capability"
    )]})
    assert check(context) is True
    permissions.replace_group_permissions({}, {})
    assert check(context) is False


@pytest.mark.parametrize("claims", [None, [], "engineering", 42])
def test_tagged_component_with_malformed_claims_is_denied(claims: object) -> None:
    permissions = InMemoryGroupConnectorToolPermissions(group_claim_fields=["groups"])
    permissions.grant_tool("engineering", "connector", "operation")
    context = cast(AuthContext, SimpleNamespace(
        tool=SimpleNamespace(get_meta=lambda: {
            "connector_id": "connector", "operation_name": "operation"
        }),
        token=SimpleNamespace(claims=claims),
    ))

    assert connector_tool_permission_check(permissions)(context) is False


@pytest.mark.parametrize("metadata", [
    {},
    {"connector_id": "connector"},
    {"connector_id": "connector", "capability_kind": "unknown", "capability_key": "key"},
    {"connector_id": 42, "capability_kind": "tool", "capability_key": "key"},
])
def test_components_without_valid_connector_identity_remain_allowed(
    metadata: dict[str, object],
) -> None:
    permissions = InMemoryGroupConnectorToolPermissions(group_claim_fields=["groups"])
    context = AuthContext(
        token=None,
        component=cast(FastMCPComponent, MetadataOnlyComponent(metadata)),
    )

    assert connector_capability_permission_check(permissions)(context) is True


def test_component_operation_name_fallback_remains_supported() -> None:
    permissions = InMemoryGroupConnectorToolPermissions(group_claim_fields=["groups"])
    permissions.grant_capability("engineering", "connector", "prompt", "operation")
    context = AuthContext(
        token=AccessToken(
            token="token", client_id="client", scopes=[], claims={"groups": "engineering"}
        ),
        component=cast(FastMCPComponent, MetadataOnlyComponent({
            "connector_id": "connector", "capability_kind": "prompt", "operation_name": "operation"
        })),
    )

    assert connector_capability_permission_check(permissions)(context) is True
