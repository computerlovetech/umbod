import asyncio
from collections.abc import AsyncIterator
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import pytest_asyncio
from pydantic import ValidationError

from tests.persistence_runtime import prepared_inmemory_runtime, prepared_sqlite_runtime
from tests.support.identity_directory import InMemoryIdentityDirectory
from umbod.core.identity_directory.models import DirectoryScope, IdentityObservation
from umbod.core.identity_directory.ports import IdentityDirectoryStore
from umbod.core.identity_directory.service import IdentityObservationService
from umbod.core.identity_directory.store import DatabaseIdentityDirectory

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def observation(**changes: object) -> IdentityObservation:
    return IdentityObservation.model_validate(
        {
            "issuer": "https://issuer",
            "subject": "subject",
            "claim": "permissions",
            "groups": (" Team/a ", "Team", "team"),
            "name": "Name",
            "email": "name@example.test",
            "email_verification": "verified",
            "observed_at": NOW,
            **changes,
        }
    )


def scope(**changes: object) -> DirectoryScope:
    return DirectoryScope.model_validate(
        {
            "issuer": "https://issuer",
            "claim": "permissions",
            "query": "",
            "limit": 50,
            **changes,
        }
    )


@pytest_asyncio.fixture(params=["port", "inmemory", "sqlite"])
async def store(
    request: pytest.FixtureRequest, tmp_path: Path
) -> AsyncIterator[IdentityDirectoryStore]:
    if request.param == "port":
        yield InMemoryIdentityDirectory()
        return
    runtime = (
        await prepared_inmemory_runtime()
        if request.param == "inmemory"
        else await prepared_sqlite_runtime(tmp_path / "directory.sqlite")
    )
    try:
        yield DatabaseIdentityDirectory(runtime.database)
    finally:
        await runtime.shutdown()


@pytest.mark.asyncio
async def test_concurrent_reordered_observations_keep_identity_and_timestamp_bounds(
    store: IdentityDirectoryStore,
) -> None:
    await store.observe(observation())
    original = (await store.search_users(scope())).users[0]
    await asyncio.gather(
        *(
            store.observe(observation(observed_at=NOW + timedelta(minutes=offset)))
            for offset in (10, -10, 0, 10, -2)
        )
    )
    user = (await store.search_users(scope())).users[0]
    assert user.user_id == original.user_id
    assert user.first_seen_at == NOW - timedelta(minutes=10)
    assert user.last_seen_at == NOW + timedelta(minutes=10)
    assert len((await store.search_groups(scope())).groups) == 3


@pytest.mark.asyncio
async def test_missing_and_older_profiles_do_not_erase_newer_fields(
    store: IdentityDirectoryStore,
) -> None:
    await store.observe(observation())
    await store.observe(
        observation(
            name="New name",
            email="new@example.test",
            email_verification="unknown",
            observed_at=NOW + timedelta(minutes=1),
        )
    )
    await store.observe(
        observation(
            name="",
            email="",
            email_verification="unknown",
            observed_at=NOW + timedelta(minutes=2),
        )
    )
    await store.observe(
        observation(
            name="Old", email="old@example.test", observed_at=NOW - timedelta(minutes=1)
        )
    )
    user = (await store.search_users(scope())).users[0]
    assert (user.name, user.email, user.email_verification) == (
        "New name",
        "new@example.test",
        "unknown",
    )


@pytest.mark.asyncio
async def test_reordered_available_profile_fills_unknown_fields(
    store: IdentityDirectoryStore,
) -> None:
    await store.observe(
        observation(
            name="",
            email="",
            email_verification="unknown",
            observed_at=NOW + timedelta(minutes=1),
        )
    )
    await store.observe(observation())
    user = (await store.search_users(scope())).users[0]
    assert (user.name, user.email, user.email_verification) == (
        "Name",
        "name@example.test",
        "verified",
    )
    assert user.last_seen_at == NOW + timedelta(minutes=1)


@pytest.mark.asyncio
async def test_new_group_and_profile_are_not_coalesced(
    store: IdentityDirectoryStore,
) -> None:
    await store.observe(observation())
    await store.observe(
        observation(
            groups=("new",), name="Changed", observed_at=NOW + timedelta(seconds=1)
        )
    )
    assert (await store.search_users(scope())).users[0].name == "Changed"
    assert [
        group.value for group in (await store.search_groups(scope(query="new"))).groups
    ] == ["new"]


@pytest.mark.asyncio
async def test_group_search_is_literal_case_insensitive_exact_and_scoped(
    store: IdentityDirectoryStore,
) -> None:
    await store.observe(observation(groups=("A%_", "a%_", "other")))
    await store.observe(observation(issuer="other", groups=("A%_hidden",)))
    await store.observe(observation(claim="admin", groups=("A%_admin",)))
    page = await store.search_groups(scope(query="a%_", limit=1))
    assert [group.value for group in page.groups] == ["A%_"]
    assert page.has_more
    assert not (await store.search_groups(scope(query="absent"))).has_more


@pytest.mark.asyncio
async def test_users_keep_distinct_provenance_and_search_known_fields(
    store: IdentityDirectoryStore,
) -> None:
    await store.observe(observation())
    await store.observe(observation(issuer="other"))
    await store.observe(observation(subject="second"))
    users = (await store.search_users(scope(query="NAME@"))).users
    assert len(users) == 2
    assert len({user.user_id for user in users}) == 2
    assert len((await store.search_users(scope(query="SECOND"))).users) == 1


@pytest.mark.asyncio
async def test_sqlite_reopen_preserves_directory_and_does_not_register_groups(
    tmp_path: Path,
) -> None:
    path = tmp_path / "directory.sqlite"
    runtime = await prepared_sqlite_runtime(path)
    store = DatabaseIdentityDirectory(runtime.database)
    await store.observe(observation())
    original = await store.search_users(scope())
    await runtime.shutdown()
    reopened = await prepared_sqlite_runtime(path)
    try:
        assert (
            await DatabaseIdentityDirectory(reopened.database).search_users(scope())
            == original
        )
        from umbod.core.groups.stores.composition import create_group_management

        assert await create_group_management(reopened.database).list_groups() == ()
    finally:
        await reopened.shutdown()


@pytest.mark.asyncio
async def test_independent_sqlite_runtimes_serialize_simultaneous_first_observations(
    tmp_path: Path,
) -> None:
    path = tmp_path / "shared.sqlite"
    first = await prepared_sqlite_runtime(path)
    second = await prepared_sqlite_runtime(path)
    try:
        stores = (
            DatabaseIdentityDirectory(first.database),
            DatabaseIdentityDirectory(second.database),
        )
        await asyncio.gather(
            stores[0].observe(observation()),
            stores[1].observe(observation(observed_at=NOW + timedelta(seconds=1))),
        )
        left = await stores[0].search_users(scope())
        right = await stores[1].search_users(scope())
        assert left == right
        assert len(left.users) == 1
        assert left.users[0].first_seen_at == NOW
        assert left.users[0].last_seen_at == NOW + timedelta(seconds=1)
    finally:
        await first.shutdown()
        await second.shutdown()


@pytest.mark.parametrize(
    "changes",
    [
        {"issuer": " "},
        {"subject": ""},
        {"groups": (" ",)},
        {"observed_at": datetime(2026, 1, 1)},
        {"email": "", "email_verification": "verified"},
    ],
)
def test_observation_validates_boundary(changes: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        observation(**changes)


@pytest.mark.asyncio
async def test_failure_logging_contains_no_exception_payload(
    caplog: pytest.LogCaptureFixture,
) -> None:
    class FailingDirectory(InMemoryIdentityDirectory):
        async def observe(self, observation: IdentityObservation) -> None:
            raise RuntimeError("secret-token email@example.test SQL")

    await IdentityObservationService(FailingDirectory()).observe_best_effort(
        observation()
    )
    assert len(caplog.records) == 1
    record = caplog.records[0]
    assert record.getMessage() == "identity_directory_observation_failed"
    assert record.exc_info is None
    assert "secret-token" not in caplog.text
