from uuid import uuid4

import pytest

from umbod.core.filesystem import (
    AccessGrant,
    NodeKind,
    NodeMetadata,
    Ownership,
    Permission,
    Principal,
    PrincipalType,
)
from umbod.core.filesystem.authorization import PermissionDenied, ResolvedIdentity
from umbod.core.persistence import PersistenceRuntime
from umbod.infrastructure import create_access_control_driver, create_namespace_driver
from tests.support.filesystem.authorization import (
    AuthorizationContext,
    caller,
    create_authorization_context,
    principal,
)


@pytest.fixture
def authorization_context(filesystem_runtime: PersistenceRuntime) -> AuthorizationContext:
    context = create_authorization_context(
        create_namespace_driver(database=filesystem_runtime.database),
        create_access_control_driver(database=filesystem_runtime.database),
    )
    context.resolver.identities[caller("alice")] = ResolvedIdentity(
        user=principal("alice", PrincipalType.USER, "provider"), groups={principal("team", PrincipalType.GROUP, "provider")}
    )
    return context


@pytest.mark.asyncio
@pytest.mark.parametrize("permission", list(Permission))
@pytest.mark.parametrize("owner", [principal("alice", PrincipalType.USER, "provider"), principal("team", PrincipalType.GROUP, "provider")])
async def test_exact_user_or_trusted_group_owner_receives_every_permission(
    authorization_context: AuthorizationContext, permission: Permission, owner: Principal
) -> None:
    context = authorization_context
    root = await context.namespace.get_root()
    await context.policies.set_owner(Ownership(node_id=root.id, owner=owner))
    decision = await context.authorization.decide(caller("alice"), root.id, permission)
    assert decision.allowed
    assert decision.node_id == root.id
    assert decision.permission == permission
    assert await context.authorization.require(caller("alice"), root.id, permission) is None


@pytest.mark.asyncio
@pytest.mark.parametrize("granted", list(Permission))
@pytest.mark.parametrize("recipient", [principal("alice", PrincipalType.USER, "provider"), principal("team", PrincipalType.GROUP, "provider")])
@pytest.mark.parametrize("recursive", [False, True])
async def test_direct_grants_confer_only_the_independent_stored_permission(
    authorization_context: AuthorizationContext, granted: Permission,
    recipient: Principal, recursive: bool,
) -> None:
    context = authorization_context
    root = await context.namespace.get_root()
    await context.policies.set_owner(Ownership(node_id=root.id, owner=principal("owner", PrincipalType.USER, "provider")))
    await context.policies.add_grant(AccessGrant(
        node_id=root.id, principal=recipient, permissions={granted}, recursive=recursive
    ))
    for requested in Permission:
        decision = await context.authorization.decide(caller("alice"), root.id, requested)
        assert decision.allowed == (requested == granted)


@pytest.mark.asyncio
@pytest.mark.parametrize("recipient", [
    principal("Alice", PrincipalType.USER, "provider"), principal("alice", PrincipalType.USER, issuer="other"),
    principal("alice", PrincipalType.GROUP, "provider"), principal("team", PrincipalType.USER, "provider"),
    principal("team", PrincipalType.GROUP, "other"), principal("administrator", PrincipalType.USER, "provider"),
])
@pytest.mark.parametrize("as_owner", [False, True])
async def test_identity_mismatch_never_confers_owner_or_grant_authority(
    authorization_context: AuthorizationContext, recipient: Principal, as_owner: bool,
) -> None:
    context = authorization_context
    root = await context.namespace.get_root()
    await context.policies.set_owner(Ownership(
        node_id=root.id, owner=recipient if as_owner else principal("owner", PrincipalType.USER, "provider")
    ))
    if not as_owner:
        await context.policies.add_grant(AccessGrant(
            node_id=root.id, principal=recipient,
            permissions=set(Permission), recursive=True,
        ))
    for permission in Permission:
        assert not (await context.authorization.decide(caller("alice"), root.id, permission)).allowed


@pytest.mark.asyncio
async def test_matching_grants_combine_without_unmatched_or_empty_grants_adding_permissions(
    authorization_context: AuthorizationContext,
) -> None:
    context = authorization_context
    root = await context.namespace.get_root()
    await context.policies.set_owner(Ownership(node_id=root.id, owner=principal("owner", PrincipalType.USER, "provider")))
    for recipient, permissions in [
        (principal("alice", PrincipalType.USER, "provider"), {Permission.READ}),
        (principal("team", PrincipalType.GROUP, "provider"), {Permission.WRITE}),
        (principal("outsider", PrincipalType.USER, "provider"), set(Permission)),
    ]:
        await context.policies.add_grant(AccessGrant(
            node_id=root.id, principal=recipient, permissions=permissions, recursive=False,
        ))
    for permission in Permission:
        decision = await context.authorization.decide(caller("alice"), root.id, permission)
        assert decision.allowed == (permission in {Permission.READ, Permission.WRITE})
    await context.policies.add_grant(AccessGrant(
        node_id=root.id, principal=principal("alice", PrincipalType.USER, "provider"), permissions=set(), recursive=True,
    ))
    assert not (await context.authorization.decide(caller("alice"), root.id, Permission.READ)).allowed


@pytest.mark.asyncio
@pytest.mark.parametrize("missing_node", [False, True])
async def test_unowned_nodes_and_orphan_policies_deny_even_with_matching_grants(
    authorization_context: AuthorizationContext, missing_node: bool,
) -> None:
    context = authorization_context
    node_id = uuid4() if missing_node else (await context.namespace.get_root()).id
    if missing_node:
        await context.policies.set_owner(Ownership(node_id=node_id, owner=principal("alice", PrincipalType.USER, "provider")))
    await context.policies.add_grant(AccessGrant(
        node_id=node_id, principal=principal("alice", PrincipalType.USER, "provider"), permissions=set(Permission), recursive=True,
    ))
    assert not (await context.authorization.decide(caller("alice"), node_id, Permission.READ)).allowed
    with pytest.raises(PermissionDenied):
        await context.authorization.require(caller("alice"), node_id, Permission.READ)


@pytest.mark.asyncio
async def test_unresolved_identity_and_absent_grants_deny_without_administrator_fallback(
    authorization_context: AuthorizationContext,
) -> None:
    context = authorization_context
    root = await context.namespace.get_root()
    await context.policies.set_owner(Ownership(node_id=root.id, owner=principal("alice", PrincipalType.USER, "provider")))
    assert not (await context.authorization.decide(caller("administrator"), root.id, Permission.READ)).allowed
    await context.policies.set_owner(Ownership(node_id=root.id, owner=principal("other", PrincipalType.USER, "provider")))
    with pytest.raises(PermissionDenied):
        await context.authorization.require(caller("alice"), root.id, Permission.READ)


@pytest.mark.asyncio
@pytest.mark.parametrize("ancestor_owner", [False, True])
async def test_ancestor_ownership_and_recursive_grants_never_authorize_descendants(
    authorization_context: AuthorizationContext, ancestor_owner: bool,
) -> None:
    context = authorization_context
    root = await context.namespace.get_root()
    child = await context.namespace.create_node(
        root.id, "child", NodeKind.FILE,
        NodeMetadata(content_type="text/plain", attributes={}),
    )
    await context.policies.set_owner(Ownership(
        node_id=root.id, owner=principal("alice" if ancestor_owner else "other", PrincipalType.USER, "provider")
    ))
    await context.policies.set_owner(Ownership(node_id=child.id, owner=principal("other", PrincipalType.USER, "provider")))
    await context.policies.add_grant(AccessGrant(
        node_id=root.id, principal=principal("alice", PrincipalType.USER, "provider"), permissions=set(Permission), recursive=True,
    ))
    for permission in Permission:
        assert not (await context.authorization.decide(caller("alice"), child.id, permission)).allowed


@pytest.mark.asyncio
async def test_repeated_decisions_observe_revocation_and_keep_callers_isolated(
    authorization_context: AuthorizationContext,
) -> None:
    context = authorization_context
    root = await context.namespace.get_root()
    await context.policies.set_owner(Ownership(node_id=root.id, owner=principal("owner", PrincipalType.USER, "provider")))
    context.resolver.identities[caller("bob")] = ResolvedIdentity(user=principal("bob", PrincipalType.USER, "provider"), groups=[])
    await context.policies.add_grant(AccessGrant(
        node_id=root.id, principal=principal("alice", PrincipalType.USER, "provider"), permissions={Permission.READ}, recursive=False,
    ))
    assert (await context.authorization.decide(caller("alice"), root.id, Permission.READ)).allowed
    assert not (await context.authorization.decide(caller("bob"), root.id, Permission.READ)).allowed
    await context.policies.remove_grant(root.id, principal("alice", PrincipalType.USER, "provider"))
    assert not (await context.authorization.decide(caller("alice"), root.id, Permission.READ)).allowed
    await context.policies.set_owner(Ownership(node_id=root.id, owner=principal("alice", PrincipalType.USER, "provider")))
    assert (await context.authorization.decide(caller("alice"), root.id, Permission.READ)).allowed
    context.resolver.identities.clear()
    assert not (await context.authorization.decide(caller("alice"), root.id, Permission.READ)).allowed
