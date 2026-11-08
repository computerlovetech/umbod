import pytest

from umbod.core.filesystem import (
    AccessGrant, NodeKind, NodeMetadata, Ownership, Permission, Principal, PrincipalType,
)
from umbod.core.filesystem.authorization import PermissionDenied, VerifiedIdentityResolver
from umbod.core.filesystem.browsing import summary
from umbod.core.filesystem.namespace import ROOT_ID
from umbod.core.persistence import PersistenceRuntime
from umbod.infrastructure import (
    create_access_control_driver, create_filesystem_access, create_filesystem_homes, create_namespace_driver,
)
from tests.umbod.core.filesystem.test_verified_identity import snapshot


@pytest.mark.asyncio
async def test_owner_metadata_reports_actual_private_policy(filesystem_runtime: PersistenceRuntime) -> None:
    database = filesystem_runtime.database
    caller = snapshot("alice", "issuer", ())
    node = await create_filesystem_homes(database=database, resolver=VerifiedIdentityResolver()).get_or_provision(caller)
    projected = (await create_filesystem_access(database=database, resolver=VerifiedIdentityResolver()).enrich_nodes(caller, [node]))[0]
    assert projected.permissions.model_dump() == {
        "can_discover": True, "can_read": True, "can_write": True, "can_delete": False, "can_share": True,
    }
    assert projected.visible_to.model_dump() == {
        "type": "available", "scope": "direct_node_policy",
        "owner": {"type": PrincipalType.USER, "issuer": "issuer", "id": "alice"},
        "grants": (), "group_members_expanded": False,
    }
    assert "permissions" not in node.model_dump()
    assert "visible_to" not in (await create_namespace_driver(database=database).get_node(node.id)).model_dump()


@pytest.mark.asyncio
@pytest.mark.parametrize("rights", [
    {Permission.DISCOVER}, {Permission.DISCOVER, Permission.READ},
    {Permission.DISCOVER, Permission.WRITE}, {Permission.DISCOVER, Permission.SHARE}, set(),
    {Permission.WRITE},
])
async def test_projection_uses_direct_matching_rights_and_fresh_revocation(
    filesystem_runtime: PersistenceRuntime, rights: set[Permission],
) -> None:
    database = filesystem_runtime.database
    owner = snapshot("alice", "issuer", ())
    node = await create_filesystem_homes(database=database, resolver=VerifiedIdentityResolver()).get_or_provision(owner)
    policies = create_access_control_driver(database=database)
    group = Principal(type=PrincipalType.GROUP, issuer="issuer", id="team")
    grant = AccessGrant(node_id=node.id, principal=group, permissions=rights, recursive=True)
    await policies.add_grant(grant)
    caller = snapshot("bob", "issuer", ("team",))
    access = create_filesystem_access(database=database, resolver=VerifiedIdentityResolver())
    if Permission.DISCOVER not in rights:
        with pytest.raises(PermissionDenied):
            await access.enrich_nodes(caller, [node])
        return
    projected = (await access.enrich_nodes(caller, [node]))[0]
    assert projected.permissions.can_read == (Permission.READ in rights)
    assert projected.permissions.can_write == (Permission.WRITE in rights)
    assert projected.permissions.can_share == (Permission.SHARE in rights)
    assert projected.visible_to.type == ("available" if Permission.SHARE in rights else "restricted")
    await policies.remove_grant(node.id, group)
    with pytest.raises(PermissionDenied):
        await access.enrich_nodes(caller, [node])


@pytest.mark.asyncio
async def test_group_union_and_foreign_unregistered_grants_are_not_filtered(
    filesystem_runtime: PersistenceRuntime,
) -> None:
    database = filesystem_runtime.database
    owner = snapshot("alice", "issuer", ())
    home = await create_filesystem_homes(database=database, resolver=VerifiedIdentityResolver()).get_or_provision(owner)
    namespace = create_namespace_driver(database=database)
    file = await namespace.create_node(home.id, "file", NodeKind.FILE, NodeMetadata(content_type={}, attributes={}))
    policies = create_access_control_driver(database=database)
    await policies.set_owner(Ownership(
        node_id=file.id, owner=Principal(type=PrincipalType.USER, issuer="issuer", id="alice"),
    ))
    grants = [
        AccessGrant(node_id=file.id, principal=Principal(type=PrincipalType.GROUP, issuer="issuer", id="one"),
                    permissions={Permission.DISCOVER, Permission.SHARE}, recursive=False),
        AccessGrant(node_id=file.id, principal=Principal(type=PrincipalType.GROUP, issuer="issuer", id="two"),
                    permissions={Permission.READ, Permission.WRITE, Permission.DELETE}, recursive=True),
        AccessGrant(node_id=file.id, principal=Principal(type=PrincipalType.USER, issuer="foreign", id="unknown"),
                    permissions={Permission.READ}, recursive=False),
    ]
    for grant in grants:
        await policies.add_grant(grant)
    access = create_filesystem_access(database=database, resolver=VerifiedIdentityResolver())
    projected = (await access.enrich_nodes(snapshot("bob", "issuer", ("one", "two")), [summary(file)]))[0]
    assert all(projected.permissions.model_dump().values())
    assert len(projected.visible_to.grants) == 3
    assert {grant.principal for grant in projected.visible_to.grants} == {grant.principal for grant in grants}
    await policies.add_grant(AccessGrant(
        node_id=file.id, principal=Principal(type=PrincipalType.SYSTEM, issuer="protected", id="policy"),
        permissions={Permission.READ}, recursive=False,
    ))
    protected = (await access.enrich_nodes(owner, [summary(file)]))[0]
    assert protected.visible_to.model_dump() == {"type": "unavailable"}


@pytest.mark.asyncio
async def test_access_metadata_cannot_disclose_missing_nodes(filesystem_runtime: PersistenceRuntime) -> None:
    from uuid import uuid4

    database = filesystem_runtime.database
    caller = snapshot("alice", "issuer", ())
    node = await create_filesystem_homes(database=database, resolver=VerifiedIdentityResolver()).get_or_provision(caller)
    access = create_filesystem_access(database=database, resolver=VerifiedIdentityResolver())
    with pytest.raises(PermissionDenied):
        await access.enrich_nodes(caller, [node.model_copy(update={"id": uuid4(), "parent_id": ROOT_ID})])


def test_visibility_serialization_canonicalizes_grants_and_permission_lists() -> None:
    from uuid import uuid4

    from umbod.core.filesystem.access import AvailableVisibility

    node_id = uuid4()
    owner = Principal(type=PrincipalType.USER, issuer="issuer", id="alice")
    grants = tuple(
        AccessGrant(node_id=node_id, principal=principal, permissions=set(Permission), recursive=False)
        for principal in (
            Principal(type=PrincipalType.USER, issuer="foreign", id="z"),
            Principal(type=PrincipalType.GROUP, issuer="issuer", id="b"),
            Principal(type=PrincipalType.GROUP, issuer="issuer", id="a"),
        )
    )
    first = AvailableVisibility(
        type="available", scope="direct_node_policy", owner=owner, grants=grants, group_members_expanded=False,
    )
    reversed_policy = first.model_copy(update={"grants": tuple(reversed(grants))})
    assert first.model_dump_json() == reversed_policy.model_dump_json()
    serialized = first.model_dump(mode="json")["grants"]
    assert [grant["principal"]["id"] for grant in serialized] == ["a", "b", "z"]
    assert all(grant["permissions"] == ["delete", "discover", "read", "share", "write"] for grant in serialized)
