import pytest

from umbod.core.callers import (
    AuthenticationProvenance,
    CallerContext,
    CallerSnapshot,
    DeclaredIssuer,
    GroupMembership,
    SubjectIdentity,
)
from umbod.core.filesystem import (
    NodeMetadata,
    Permission,
    Principal,
    PrincipalType,
    RootBootstrapGrant,
    RootBootstrapSpec,
)
from umbod.core.filesystem.authorization import PermissionDenied, VerifiedIdentityResolver
from umbod.core.persistence import PersistenceRuntime
from umbod.infrastructure import (
    create_filesystem_browsing,
    create_filesystem_creation,
    create_root_provisioning,
)


def verified_snapshot(subject: str) -> CallerSnapshot:
    return CallerSnapshot(
        caller=CallerContext(
            authentication=AuthenticationProvenance.UPSTREAM_VERIFIED,
            subject=SubjectIdentity(issuer=DeclaredIssuer(value="issuer"), subject=subject),
        ),
        groups=GroupMembership(group_ids=("members",)),
    )


@pytest.mark.asyncio
async def test_separately_composed_delivery_services_share_namespace_and_private_ownership(
    filesystem_runtime: PersistenceRuntime,
) -> None:
    database = filesystem_runtime.database
    root = await create_root_provisioning(database=database).provision(RootBootstrapSpec(grants=(
        RootBootstrapGrant(
            principal=Principal(type=PrincipalType.GROUP, issuer="issuer", id="members"),
            permissions=frozenset({Permission.DISCOVER, Permission.WRITE}),
        ),
    )))
    creation = create_filesystem_creation(database=database, resolver=VerifiedIdentityResolver())
    browsing = create_filesystem_browsing(database=database, resolver=VerifiedIdentityResolver())
    created = await creation.create_file(
        verified_snapshot("alice"), root.id, "private", NodeMetadata(content_type="text/plain", attributes={}),
    )
    assert await browsing.get_node(verified_snapshot("alice"), created.id) == created
    assert list(await browsing.list_children(verified_snapshot("alice"), root.id)) == [created]
    assert list(await browsing.list_children(verified_snapshot("bob"), root.id)) == []
    with pytest.raises(PermissionDenied):
        await browsing.get_node(verified_snapshot("bob"), created.id)
