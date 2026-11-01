from typing import Optional
from uuid import uuid4

import pytest
from pydantic import ValidationError

from umbod.core.filesystem import AccessGrant, Permission, Principal, PrincipalType
from umbod.core.filesystem.authorization import PermissionDenied, VerifiedIdentityResolver
from umbod.core.filesystem.namespace import initial_root
from umbod.core.filesystem.sharing import InvalidSharingPolicy, ShareNodeResult, SharingService, ShareNodePolicy, UserSharingTarget
from umbod.core.identity_directory.user_models import ObservedUserIdentity, ObservedUserProfile, SubjectUsersLookup, UserLookup
from tests.support.identity_directory import InMemoryIdentityDirectory
from tests.umbod.core.filesystem.test_authorized_content import caller
from tests.umbod.core.filesystem.test_verified_identity import snapshot
from .test_ports import transactions
from .test_additive_ports import CountingTransactions
from .test_user_policy import observe, user_command


class UnreadableUsers(InMemoryIdentityDirectory):
    async def find_user_identity(self, lookup: UserLookup) -> Optional[ObservedUserIdentity]:
        raise AssertionError("Directory must not be accessed")

    async def find_subject_users(self, lookup: SubjectUsersLookup) -> tuple[ObservedUserProfile, ...]:
        raise AssertionError("Directory must not be accessed")


@pytest.mark.asyncio
@pytest.mark.parametrize("permissions", [set(), {Permission.SHARE}, {Permission.DISCOVER}, {Permission.READ, Permission.WRITE}])
async def test_current_direct_authority_is_checked_before_any_user_lookup(permissions: set[Permission]) -> None:
    ports = transactions()
    ports.users = UnreadableUsers()
    node_id = initial_root().id
    await ports.policies.add_grant(AccessGrant(
        node_id=node_id, principal=Principal(type=PrincipalType.USER, issuer="issuer", id="delegate"),
        permissions=permissions, recursive=False,
    ))
    service = SharingService(VerifiedIdentityResolver(), ports, "issuer")
    for target in (node_id, uuid4()):
        actor = snapshot("delegate", "issuer", ())
        with pytest.raises(PermissionDenied):
            await service.share(actor, target, user_command("missing", Permission.READ))


@pytest.mark.asyncio
@pytest.mark.parametrize("recursive,permissions", [
    (False, {"invalid"}), (None, {Permission.READ}), (0, {Permission.READ}), ("", {Permission.READ}),
])
async def test_malformed_same_principal_grant_blocks_share_and_summary_without_disclosure(
    recursive: object, permissions: set[object],
) -> None:
    ports = transactions()
    user_id = await observe(ports.users, "issuer", "recipient")
    node_id = initial_root().id
    grant = AccessGrant.model_construct(
        node_id=node_id, principal=Principal(type=PrincipalType.USER, issuer="issuer", id="recipient"),
        permissions=permissions, recursive=recursive,
    )
    await ports.policies.add_grant(grant)
    service = SharingService(VerifiedIdentityResolver(), ports, "issuer")
    summary = (await service.summarize_nodes(caller(), (node_id,))).nodes[0]
    assert summary.can_share and summary.grants == ()
    with pytest.raises(InvalidSharingPolicy):
        await service.share(caller(), node_id, user_command(user_id, Permission.READ))
    assert await ports.policies.list_grants(node_id) == [grant]


@pytest.mark.asyncio
async def test_subset_user_sharing_performs_no_write_but_validates_current_authority() -> None:
    ports = CountingTransactions(transactions())
    user_id = await observe(ports.ports.users, "issuer", "delegate")
    node_id = initial_root().id
    service = SharingService(VerifiedIdentityResolver(), ports, "issuer")
    command = user_command(user_id, Permission.READ)
    await service.share(caller(), node_id, command)
    assert not (await service.share(caller(), node_id, command)).changed
    assert ports.grants.writes == 1
    with pytest.raises(PermissionDenied):
        await service.share(snapshot("delegate", "issuer", ()), node_id, command)
    assert ports.grants.writes == 1


@pytest.mark.parametrize("overrides", [
    {"user_id": ""}, {"user_id": " \t"}, {"user_id": 123}, {"user_id": "x" * 201},
    {"issuer": "foreign"}, {"subject": "recipient"}, {"label": "Display Name"},
])
def test_user_target_rejects_invalid_fields(overrides: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        UserSharingTarget.model_validate({"type": "user", "user_id": " exact "} | overrides)


@pytest.mark.parametrize("permissions", [[], ["invalid"]])
def test_user_share_policy_rejects_invalid_permissions(permissions: list[str]) -> None:
    with pytest.raises(ValidationError):
        ShareNodePolicy.model_validate({
            "recipient": {"type": "user", "user_id": " exact "}, "permissions": permissions,
        })


def test_user_result_is_frozen_preserves_exact_identifier_and_sorts_permissions() -> None:
    result = ShareNodeResult(
        node_id=initial_root().id, recipient=UserSharingTarget(type="user", user_id=" exact "), changed=False,
        permissions=frozenset({Permission.WRITE, Permission.READ, Permission.DISCOVER}),
    )
    assert result.recipient.user_id == " exact "
    assert result.model_dump(mode="json")["permissions"] == ["discover", "read", "write"]
    assert ShareNodeResult.model_validate_json(result.model_dump_json()) == result
    with pytest.raises(ValidationError):
        result.changed = True
