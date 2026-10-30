from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import pytest
from pydantic import ValidationError

from umbod.core.callers import CallerSnapshot
from umbod.core.filesystem import AccessGrant, Permission
from umbod.core.filesystem.authorization import (
    PermissionDenied, ResolvedIdentity, UnresolvedIdentity, VerifiedIdentityResolver,
)
from umbod.core.filesystem.namespace import initial_root
from umbod.core.filesystem.sharing import (
    FilesystemSharing, GroupPolicy, InvalidSharingPolicy, ShareNodeGroupResult, SharingService,
)
from umbod.core.filesystem.sharing.ports import SharingSession
from tests.support.filesystem.group_sharing import (
    InMemorySharingSession, InMemorySharingTransactions, SharingPolicies,
)
from tests.umbod.core.filesystem.test_authorized_content import caller
from tests.umbod.core.filesystem.test_verified_identity import snapshot
from .test_ports import transactions


class CountingResolver:
    def __init__(self) -> None:
        self.resolutions = 0

    async def resolve(self, snapshot: CallerSnapshot) -> ResolvedIdentity | UnresolvedIdentity:
        self.resolutions += 1
        return await VerifiedIdentityResolver().resolve(snapshot)


class CountingGrants:
    def __init__(self, policies: SharingPolicies) -> None:
        self.policies = policies
        self.writes = 0

    async def upsert(self, grant: AccessGrant) -> None:
        self.writes += 1
        await self.policies.upsert(grant)


class CountingTransactions:
    def __init__(self, ports: InMemorySharingTransactions) -> None:
        self.ports = ports
        self.grants = CountingGrants(ports.policies)
        self.transactions = 0

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[SharingSession]:
        self.transactions += 1
        async with self.ports.transaction() as session:
            yield InMemorySharingSession(
                namespace=session.namespace, access_control=session.access_control,
                groups=session.groups, grants=self.grants,
            )


@pytest.mark.asyncio
async def test_public_share_unions_permissions_and_skips_repeat_and_subset_writes() -> None:
    ports = CountingTransactions(transactions())
    resolver = CountingResolver()
    service: FilesystemSharing = SharingService(resolver, ports, "issuer")
    node_id = initial_root().id
    read = GroupPolicy(group_id="team", permissions=frozenset({Permission.READ}))
    discover = GroupPolicy(group_id="team", permissions=frozenset({Permission.DISCOVER}))
    first = await service.share(caller(), node_id, read)
    assert first == ShareNodeGroupResult(node_id=node_id, group_id="team", permissions=read.permissions, changed=True)
    added = await service.share(caller(), node_id, discover)
    assert added.permissions == read.permissions | discover.permissions
    assert added.changed
    for command in (discover, read, GroupPolicy(group_id="team", permissions=added.permissions)):
        result = await service.share(caller(), node_id, command)
        assert result.permissions == added.permissions
        assert not result.changed
    assert ports.grants.writes == 2
    assert ports.transactions == 5
    assert resolver.resolutions == 5
    assert (await service.inspect(caller(), node_id)).groups == (GroupPolicy(group_id="team", permissions=added.permissions),)


@pytest.mark.asyncio
async def test_repeat_still_checks_current_authority_and_registration() -> None:
    ports = CountingTransactions(transactions())
    service: FilesystemSharing = SharingService(VerifiedIdentityResolver(), ports, "issuer")
    command = GroupPolicy(group_id="team", permissions=frozenset({Permission.READ}))
    await service.share(caller(), initial_root().id, command)
    with pytest.raises(PermissionDenied):
        await service.share(snapshot("admin", "issuer", ("admins",)), initial_root().id, command)
    ports.ports.groups.identifiers = frozenset()
    with pytest.raises(InvalidSharingPolicy):
        await service.share(caller(), initial_root().id, command)
    assert ports.grants.writes == 1


@pytest.mark.parametrize("overrides", [
    {"node_id": None}, {"group_id": ""}, {"group_id": " \t"}, {"group_id": 123},
    {"permissions": []}, {"permissions": ["invalid"]}, {"permissions": None},
    {"changed": None}, {"issuer": "foreign"},
])
def test_result_rejects_invalid_fields(overrides: dict[str, object]) -> None:
    payload: dict[str, object] = {
        "node_id": initial_root().id, "group_id": " Team ",
        "permissions": [Permission.READ], "changed": True,
    }
    with pytest.raises(ValidationError):
        ShareNodeGroupResult.model_validate(payload | overrides)


@pytest.mark.parametrize("missing", ["node_id", "group_id", "permissions", "changed"])
def test_result_requires_all_fields(missing: str) -> None:
    payload: dict[str, object] = {
        "node_id": initial_root().id, "group_id": "team",
        "permissions": [Permission.READ], "changed": True,
    }
    del payload[missing]
    with pytest.raises(ValidationError):
        ShareNodeGroupResult.model_validate(payload)


def test_result_is_frozen_preserves_exact_id_and_sorts_json_permissions() -> None:
    result = ShareNodeGroupResult(
        node_id=initial_root().id, group_id=" Team ",
        permissions=frozenset({Permission.WRITE, Permission.DISCOVER, Permission.READ}),
        changed=False,
    )
    assert result.group_id == " Team "
    assert result.model_dump(mode="json")["permissions"] == ["discover", "read", "write"]
    assert ShareNodeGroupResult.model_validate_json(result.model_dump_json()) == result
    with pytest.raises(ValidationError):
        result.changed = True
