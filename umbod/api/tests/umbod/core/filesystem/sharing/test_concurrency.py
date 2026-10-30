import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import pytest

from umbod.core.filesystem import AccessGrant, RevisionConflict, StorageFailure
from umbod.core.filesystem.authorization import VerifiedIdentityResolver
from umbod.core.filesystem.sharing import InvalidSharingPolicy, ReplaceNodeGroupPolicy, SharingService
from umbod.core.filesystem.sharing.ports import SharingSession, SharingTransactions
from umbod.core.filesystem.stores.sharing import DatabaseSharingSession, DatabaseSharingTransactions
from umbod.core.groups import GroupInUse, RegisterGroup
from umbod.core.groups.stores.composition import shared_group_usage
from umbod.core.groups.stores.service import DatabaseGroupCatalogue
from tests.persistence_runtime import prepared_sqlite_runtime
from tests.umbod.core.filesystem.test_authorized_content import caller
from .conftest import SharingContext, sharing_context
from .test_policy import group, replace


class GatedGrants:
    def __init__(self, session: SharingSession, checked: asyncio.Event, release: asyncio.Event) -> None:
        self._session = session
        self._checked = checked
        self._release = release

    async def upsert(self, grant: AccessGrant) -> None:
        self._checked.set()
        await self._release.wait()
        await self._session.grants.upsert(grant)


class GatedTransactions:
    def __init__(self, transactions: SharingTransactions, checked: asyncio.Event, release: asyncio.Event) -> None:
        self._transactions = transactions
        self._checked = checked
        self._release = release

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[SharingSession]:
        async with self._transactions.transaction() as session:
            yield DatabaseSharingSession(
                namespace=session.namespace, access_control=session.access_control,
                groups=session.groups, grants=GatedGrants(session, self._checked, self._release),
            )


@pytest.mark.asyncio
async def test_sharing_first_blocks_group_deletion_until_reference_is_committed(context: SharingContext) -> None:
    await context.groups.register_group(RegisterGroup(group_id="team"))
    before = await context.service.inspect(caller(), context.node.id)
    checked, release, started = asyncio.Event(), asyncio.Event(), asyncio.Event()
    service = SharingService(VerifiedIdentityResolver(), GatedTransactions(DatabaseSharingTransactions(context.database), checked, release), "issuer")
    sharing = asyncio.create_task(service.replace(caller(), context.node.id, ReplaceNodeGroupPolicy(expected_revision=before.revision, groups=(group("team"),))))
    await asyncio.wait_for(checked.wait(), 5)

    async def delete() -> None:
        started.set()
        await context.groups.delete_group("team")

    deletion = asyncio.create_task(delete())
    await started.wait()
    assert not deletion.done()
    release.set()
    await sharing
    with pytest.raises(GroupInUse):
        await deletion
    assert (await context.service.inspect(caller(), context.node.id)).groups == (group("team"),)


@pytest.mark.asyncio
async def test_group_deletion_first_rejects_sharing_without_resurrection(context: SharingContext) -> None:
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
        await context.service.replace(caller(), context.node.id, ReplaceNodeGroupPolicy(expected_revision=before.revision, groups=(group("team"),)))

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
@pytest.mark.parametrize("attempt", range(3))
async def test_separate_sqlite_connections_have_exactly_one_replacement_winner(tmp_path: Path, attempt: int) -> None:
    path = tmp_path / f"sharing-{attempt}.db"
    first = await prepared_sqlite_runtime(path)
    second = await prepared_sqlite_runtime(path)
    try:
        context = await sharing_context(first.database)
        for identifier in ("first", "second"):
            await context.groups.register_group(RegisterGroup(group_id=identifier))
        before = await context.service.inspect(caller(), context.node.id)
        services = (
            SharingService(VerifiedIdentityResolver(), DatabaseSharingTransactions(first.database), "issuer"),
            SharingService(VerifiedIdentityResolver(), DatabaseSharingTransactions(second.database), "issuer"),
        )
        results = await asyncio.gather(*(
            service.replace(caller(), context.node.id, ReplaceNodeGroupPolicy(expected_revision=before.revision, groups=(group(identifier),)))
            for service, identifier in zip(services, ("first", "second"), strict=True)
        ), return_exceptions=True)
        assert sum(isinstance(result, RevisionConflict) for result in results) == 1
        winners = [result for result in results if not isinstance(result, BaseException)]
        assert len(winners) == 1
        assert await context.service.inspect(caller(), context.node.id) == winners[0]
    finally:
        await second.shutdown()
        await first.shutdown()


class FailingGrants:
    def __init__(self, session: SharingSession, failure: BaseException) -> None:
        self._session = session
        self._failure = failure
        self._written = False

    async def upsert(self, grant: AccessGrant) -> None:
        if self._written:
            raise self._failure
        await self._session.grants.upsert(grant)
        self._written = True


class FailingTransactions:
    def __init__(self, transactions: SharingTransactions, failure: BaseException) -> None:
        self._transactions = transactions
        self._failure = failure

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[SharingSession]:
        async with self._transactions.transaction() as session:
            yield DatabaseSharingSession(
                namespace=session.namespace, access_control=session.access_control,
                groups=session.groups, grants=FailingGrants(session, self._failure),
            )


@pytest.mark.asyncio
@pytest.mark.parametrize("cancelled", [False, True])
async def test_partial_replacement_failure_restores_exact_policy(context: SharingContext, cancelled: bool) -> None:
    for identifier in ("old", "first", "second"):
        await context.groups.register_group(RegisterGroup(group_id=identifier))
    await replace(context, (group("old"),))
    before = await context.service.inspect(caller(), context.node.id)
    failure = asyncio.CancelledError() if cancelled else RuntimeError("private persistence failure")
    service = SharingService(VerifiedIdentityResolver(), FailingTransactions(DatabaseSharingTransactions(context.database), failure), "issuer")
    with pytest.raises(asyncio.CancelledError if cancelled else StorageFailure):
        await service.replace(caller(), context.node.id, ReplaceNodeGroupPolicy(expected_revision=before.revision, groups=(group("first"), group("second"))))
    assert await context.service.inspect(caller(), context.node.id) == before
