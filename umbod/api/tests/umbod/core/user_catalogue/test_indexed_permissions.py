from typing import cast
from unittest.mock import AsyncMock

import pytest

from umbod.core.capabilities.availability import CapabilityPermissionPolicy
from umbod.core.capabilities.domain import CapabilityIdentity, CapabilityKind
from umbod.core.invocation import ConnectorKind
from umbod.core.permissions.domain import ConnectorCapabilityRef, GroupPermissionSet
from umbod.core.permissions.ports import GroupPermissionLookup
from umbod.core.user_catalogue.shared import IndexedCapabilityPermissions


def identity(
    connector_kind: ConnectorKind, connector_id: str, capability_kind: CapabilityKind, key: str,
) -> CapabilityIdentity:
    return CapabilityIdentity(
        connector_kind=connector_kind, connector_id=connector_id,
        capability_kind=capability_kind, capability_key=key,
    )


class CurrentGrants:
    def __init__(self, groups: dict[str, GroupPermissionSet]) -> None:
        self.groups = groups
        self.calls: list[str] = []

    async def list_group_permissions(self, group_id: str) -> GroupPermissionSet:
        self.calls.append(group_id)
        return self.groups.get(group_id, GroupPermissionSet(group_id, (), ()))


@pytest.mark.asyncio
@pytest.mark.parametrize("connector_kind", ["native", "openapi", "downstream_mcp"])
async def test_index_captures_each_group_once_and_reuses_union_for_all_checks(
    connector_kind: ConnectorKind,
) -> None:
    read = ConnectorCapabilityRef("connector", "tool", "read")
    prompt = ConnectorCapabilityRef("connector", "prompt", "prompt")
    grants = CurrentGrants({
        "first": GroupPermissionSet("first", (), (read, read)),
        "second": GroupPermissionSet("second", (), (read, prompt)),
    })
    policy: CapabilityPermissionPolicy = await IndexedCapabilityPermissions.capture(
        grants, ("first", "second", "first"),
    )
    grants.groups.clear()
    for _ in range(200):
        assert await policy.allows(identity(connector_kind, "connector", "tool", "read"))
        assert await policy.allows(identity(connector_kind, "connector", "prompt", "prompt"))
        assert not await policy.allows(identity(connector_kind, "connector", "tool", "denied"))
    assert grants.calls == ["first", "second"]


@pytest.mark.asyncio
@pytest.mark.parametrize("connector_id,capability_kind,key", [
    ("other", "tool", "read"),
    ("connector", "prompt", "read"),
    ("connector", "resource", "read"),
    ("connector", "resource_template", "read"),
    ("connector", "tool", "other"),
])
async def test_index_requires_exact_explicit_capability_grant(
    connector_id: str, capability_kind: CapabilityKind, key: str,
) -> None:
    grants = CurrentGrants({"team": GroupPermissionSet(
        "team", ("connector", "other"), (ConnectorCapabilityRef("connector", "tool", "read"),),
    )})
    policy: CapabilityPermissionPolicy = await IndexedCapabilityPermissions.capture(grants, ("team",))
    assert not await policy.allows(identity("native", connector_id, capability_kind, key))


@pytest.mark.asyncio
@pytest.mark.parametrize("groups", [(), ("missing",), ("connector-only",)])
async def test_empty_missing_and_connector_only_grants_deny_capabilities(groups: tuple[str, ...]) -> None:
    grants = CurrentGrants({
        "connector-only": GroupPermissionSet("connector-only", ("connector",), ()),
        "other-owner": GroupPermissionSet("other-owner", (), (ConnectorCapabilityRef("connector", "tool", "read"),)),
    })
    policy: CapabilityPermissionPolicy = await IndexedCapabilityPermissions.capture(grants, groups)
    assert not await policy.allows(identity("native", "connector", "tool", "read"))
    assert grants.calls == list(groups)


@pytest.mark.asyncio
async def test_new_capture_observes_revocation_without_mutating_previous_request() -> None:
    grants = CurrentGrants({"team": GroupPermissionSet(
        "team", (), (ConnectorCapabilityRef("connector", "tool", "read"),),
    )})
    previous: CapabilityPermissionPolicy = await IndexedCapabilityPermissions.capture(grants, ("team",))
    grants.groups["team"] = GroupPermissionSet("team", (), ())
    current: CapabilityPermissionPolicy = await IndexedCapabilityPermissions.capture(grants, ("team",))
    target = identity("native", "connector", "tool", "read")
    assert await previous.allows(target)
    assert not await current.allows(target)
    assert grants.calls == ["team", "team"]


@pytest.mark.asyncio
async def test_failed_group_capture_does_not_return_partial_policy() -> None:
    lookup = AsyncMock(spec=GroupPermissionLookup)
    lookup.list_group_permissions.side_effect = [
        GroupPermissionSet("first", (), (ConnectorCapabilityRef("connector", "tool", "read"),)),
        RuntimeError("Grant lookup unavailable"),
    ]
    with pytest.raises(RuntimeError, match="Grant lookup unavailable"):
        await IndexedCapabilityPermissions.capture(cast(GroupPermissionLookup, lookup), ("first", "second"))
