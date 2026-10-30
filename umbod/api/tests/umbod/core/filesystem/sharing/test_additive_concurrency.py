import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
import pytest_asyncio

from umbod.core.filesystem import AccessGrant, Permission, RevisionConflict, StorageFailure
from umbod.core.filesystem.authorization import PermissionDenied, VerifiedIdentityResolver
from umbod.core.filesystem.sharing import (
    FilesystemSharing, InvalidSharingPolicy, ReplaceNodeGroupPolicy, ShareNodeGroupResult,
    SharingService,
)
from umbod.core.filesystem.sharing.ports import SharingSession, SharingTransactions
from umbod.core.filesystem.stores.access_control import SessionAccessControl
from umbod.core.filesystem.stores.sharing import DatabaseSharingSession, DatabaseSharingTransactions
from umbod.core.groups import GroupInUse, RegisterGroup
from umbod.core.groups.stores.composition import create_group_management, shared_group_usage
from umbod.core.groups.stores.service import DatabaseGroupCatalogue
from umbod.core.persistence import Database, TransactionMode
from tests.persistence_runtime import prepared_sqlite_runtime
from tests.umbod.core.filesystem.test_authorized_content import caller
from tests.umbod.core.filesystem.test_verified_identity import snapshot
from .conftest import SharingContext, sharing_context
from .test_additive_policy import command
from .test_concurrency import GatedTransactions
from .test_policy import principal


@pytest_asyncio.fixture
async def independent_connections(tmp_path: Path) -> AsyncIterator[tuple[SharingContext, Database]]:
    path = tmp_path / "additive-sharing.db"
    first = await prepared_sqlite_runtime(path)
    second = await prepared_sqlite_runtime(path)
    try:
        yield await sharing_context(first.database), second.database
    finally:
        await second.shutdown()
        await first.shutdown()


def sharing_service(database: Database) -> FilesystemSharing:
    return SharingService(VerifiedIdentityResolver(), DatabaseSharingTransactions(database), "issuer")


@pytest.mark.asyncio
@pytest.mark.parametrize("scenario", ["same-group", "different-groups", "identical"])
async def test_independent_connections_serialize_additive_requests_without_lost_updates(
    independent_connections: tuple[SharingContext, Database], scenario: str,
) -> None:
    context, second = independent_connections
    for identifier in ("team", "other"):
        await context.groups.register_group(RegisterGroup(group_id=identifier))
    checked, release, started = asyncio.Event(), asyncio.Event(), asyncio.Event()
    gated = SharingService(VerifiedIdentityResolver(), GatedTransactions(DatabaseSharingTransactions(context.database), checked, release), "issuer")
    first_command = command("team", Permission.READ)
    second_command = command("other" if scenario == "different-groups" else "team", Permission.READ if scenario == "identical" else Permission.WRITE)
    first = asyncio.create_task(gated.share(caller(), context.node.id, first_command))
    await asyncio.wait_for(checked.wait(), 5)

    async def share_second() -> ShareNodeGroupResult:
        started.set()
        return await sharing_service(second).share(caller(), context.node.id, second_command)

    later = asyncio.create_task(share_second())
    await started.wait()
    assert not later.done()
    release.set()
    first_result, second_result = await asyncio.gather(first, later)
    assert first_result.changed
    view = await context.service.inspect(caller(), context.node.id)
    if scenario == "different-groups":
        assert second_result.changed
        assert view.groups == (second_command, first_command)
    elif scenario == "same-group":
        assert second_result.changed
        assert second_result.permissions == frozenset({Permission.READ, Permission.WRITE})
        assert view.groups == (command("team", Permission.READ, Permission.WRITE),)
    else:
        assert not second_result.changed
        assert view.groups == (first_command,)


@pytest.mark.asyncio
async def test_additive_share_commits_before_independent_group_deletion(
    independent_connections: tuple[SharingContext, Database],
) -> None:
    context, second = independent_connections
    await context.groups.register_group(RegisterGroup(group_id="team"))
    checked, release, started = asyncio.Event(), asyncio.Event(), asyncio.Event()
    gated = SharingService(VerifiedIdentityResolver(), GatedTransactions(DatabaseSharingTransactions(context.database), checked, release), "issuer")
    sharing = asyncio.create_task(gated.share(caller(), context.node.id, command("team", Permission.READ)))
    await asyncio.wait_for(checked.wait(), 5)

    async def delete() -> None:
        started.set()
        await create_group_management(second).delete_group("team")

    deletion = asyncio.create_task(delete())
    await started.wait()
    assert not deletion.done()
    release.set()
    assert (await sharing).changed
    with pytest.raises(GroupInUse):
        await deletion
    assert (await context.service.inspect(caller(), context.node.id)).groups == (command("team", Permission.READ),)


@pytest.mark.asyncio
async def test_independent_group_deletion_before_additive_share_prevents_resurrection(
    independent_connections: tuple[SharingContext, Database],
) -> None:
    context, second = independent_connections
    await context.groups.register_group(RegisterGroup(group_id="team"))
    before = await context.service.inspect(caller(), context.node.id)
    checked, release, started = asyncio.Event(), asyncio.Event(), asyncio.Event()
    catalogue = DatabaseGroupCatalogue(context.database, shared_group_usage)

    async def delete() -> None:
        async with catalogue.write() as session:
            assert not await session.is_in_use("team")
            await session.delete("team")
            checked.set()
            await release.wait()

    async def share() -> None:
        started.set()
        await sharing_service(second).share(caller(), context.node.id, command("team", Permission.READ))

    deletion = asyncio.create_task(delete())
    await asyncio.wait_for(checked.wait(), 5)
    sharing = asyncio.create_task(share())
    await started.wait()
    assert not sharing.done()
    release.set()
    await deletion
    with pytest.raises(InvalidSharingPolicy):
        await sharing
    assert await context.groups.list_groups() == ()
    assert await context.service.inspect(caller(), context.node.id) == before


@pytest.mark.asyncio
async def test_independent_revocation_before_additive_share_denies_current_authority(
    independent_connections: tuple[SharingContext, Database],
) -> None:
    context, second = independent_connections
    await context.groups.register_group(RegisterGroup(group_id="recipient"))
    await context.policies.add_grant(AccessGrant(node_id=context.node.id, principal=principal("delegates"), permissions={Permission.DISCOVER, Permission.SHARE}, recursive=False))
    checked, release, started = asyncio.Event(), asyncio.Event(), asyncio.Event()

    async def revoke() -> None:
        async with context.database.session(mode=TransactionMode.SERIALIZED_WRITE) as session:
            await SessionAccessControl(session).remove_grant(context.node.id, principal("delegates"))
            checked.set()
            await release.wait()

    async def share() -> None:
        started.set()
        await sharing_service(second).share(snapshot("bob", "issuer", ("delegates",)), context.node.id, command("recipient", Permission.READ))

    revocation = asyncio.create_task(revoke())
    await asyncio.wait_for(checked.wait(), 5)
    sharing = asyncio.create_task(share())
    await started.wait()
    assert not sharing.done()
    release.set()
    await revocation
    with pytest.raises(PermissionDenied):
        await sharing
    assert await context.policies.list_grants(context.node.id) == []


@pytest.mark.asyncio
async def test_independent_additive_commit_invalidates_old_replace_and_allows_fresh_replace(
    independent_connections: tuple[SharingContext, Database],
) -> None:
    context, second = independent_connections
    await context.groups.register_group(RegisterGroup(group_id="team"))
    before = await context.service.inspect(caller(), context.node.id)
    await sharing_service(second).share(caller(), context.node.id, command("team", Permission.READ))
    with pytest.raises(RevisionConflict):
        await context.service.replace(caller(), context.node.id, ReplaceNodeGroupPolicy(expected_revision=before.revision, groups=()))
    current = await context.service.inspect(caller(), context.node.id)
    result = await sharing_service(second).replace(caller(), context.node.id, ReplaceNodeGroupPolicy(expected_revision=current.revision, groups=()))
    assert result.groups == ()
    assert await context.service.inspect(caller(), context.node.id) == result


class WriteThenFailGrants:
    def __init__(self, session: SharingSession, failure: BaseException) -> None:
        self.session = session
        self.failure = failure

    async def upsert(self, grant: AccessGrant) -> None:
        await self.session.grants.upsert(grant)
        raise self.failure


class WriteThenFailTransactions:
    def __init__(self, transactions: SharingTransactions, failure: BaseException) -> None:
        self.transactions = transactions
        self.failure = failure

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[SharingSession]:
        async with self.transactions.transaction() as session:
            yield DatabaseSharingSession(
                namespace=session.namespace, access_control=session.access_control,
                groups=session.groups, grants=WriteThenFailGrants(session, self.failure),
            )


@pytest.mark.asyncio
@pytest.mark.parametrize("cancelled", [False, True])
async def test_additive_write_error_or_cancellation_restores_previous_policy(context: SharingContext, cancelled: bool) -> None:
    await context.groups.register_group(RegisterGroup(group_id="team"))
    await context.service.share(caller(), context.node.id, command("team", Permission.READ))
    before = await context.service.inspect(caller(), context.node.id)
    groups = await context.groups.list_groups()
    failure = asyncio.CancelledError() if cancelled else RuntimeError("private storage failure")
    service: FilesystemSharing = SharingService(VerifiedIdentityResolver(), WriteThenFailTransactions(DatabaseSharingTransactions(context.database), failure), "issuer")
    with pytest.raises(asyncio.CancelledError if cancelled else StorageFailure):
        await service.share(caller(), context.node.id, command("team", Permission.WRITE))
    assert await context.service.inspect(caller(), context.node.id) == before
    assert await context.groups.list_groups() == groups
