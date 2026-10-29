from asyncio import Event, create_task, wait_for
from collections.abc import AsyncIterator
from pathlib import Path
from uuid import uuid4

import pytest
import pytest_asyncio
from pydantic import ValidationError

from tests.persistence_runtime import prepared_inmemory_runtime, prepared_sqlite_runtime
from umbod.core.groups import (
    GroupCatalogue,
    GroupInUse,
    GroupManagementService,
    RegisterGroup,
)
from tests.support.groups import InMemoryGroupCatalogue
from umbod.core.groups.stores.composition import (
    create_group_management,
    shared_group_usage,
)
from umbod.core.groups.stores.service import DatabaseGroupCatalogue
from umbod.core.persistence import Database, TransactionMode
from umbod.core.filesystem.models import (
    AccessGrant,
    Ownership,
    Principal,
    PrincipalType,
)
from umbod.core.filesystem.stores.access_control import (
    DatabaseAccessControl,
    SessionAccessControl,
)
from umbod.core.permissions.domain import (
    SaveGroupPermissionsRequest,
    ConnectorCapabilityRef,
)
from umbod.core.permissions.factories import create_group_permission_store


class NoGroupUsage:
    async def is_in_use(self, group_id: str) -> bool:
        return False


@pytest_asyncio.fixture(params=["in_memory", "sqlite"])
async def database(
    request: pytest.FixtureRequest, tmp_path: Path
) -> AsyncIterator[Database]:
    runtime = (
        await prepared_sqlite_runtime(tmp_path / "groups.sqlite3")
        if request.param == "sqlite"
        else await prepared_inmemory_runtime()
    )
    try:
        yield runtime.database
    finally:
        await runtime.shutdown()


@pytest_asyncio.fixture(params=["memory", "database"])
async def catalogue(
    request: pytest.FixtureRequest, database: Database
) -> GroupCatalogue:
    if request.param == "memory":
        return InMemoryGroupCatalogue(NoGroupUsage())
    return DatabaseGroupCatalogue(database, shared_group_usage)


@pytest.mark.asyncio
async def test_registration_is_exact_idempotent_and_grants_nothing(
    catalogue: GroupCatalogue,
) -> None:
    management = GroupManagementService(catalogue)
    for group_id in ("Team", "team", " team ", "a/b", "Team"):
        await management.register_group(RegisterGroup(group_id=group_id))
    assert tuple(group.group_id for group in await management.list_groups()) == (
        " team ",
        "Team",
        "a/b",
        "team",
    )
    await management.delete_group("missing")
    await management.delete_group("a/b")
    assert "a/b" not in {group.group_id for group in await management.list_groups()}


@pytest.mark.parametrize("group_id", ["", " ", "\n\t"])
def test_new_registration_rejects_blank_values(group_id: str) -> None:
    with pytest.raises(ValidationError):
        RegisterGroup(group_id=group_id)


@pytest.mark.asyncio
async def test_catalogue_transaction_rolls_back(catalogue: GroupCatalogue) -> None:
    with pytest.raises(RuntimeError):
        async with catalogue.write() as session:
            await session.register("rolled-back")
            raise RuntimeError("abort")
    assert await catalogue.list_groups() == ()


def group_principal(group_id: str, issuer: str) -> Principal:
    return Principal(type=PrincipalType.GROUP, issuer=issuer, id=group_id)


@pytest.mark.asyncio
@pytest.mark.parametrize("recursive", [False, True])
async def test_all_node_empty_or_recursive_grants_block_deletion(
    database: Database, recursive: bool
) -> None:
    management = create_group_management(database)
    policies = DatabaseAccessControl(database)
    grant = AccessGrant(
        node_id=uuid4(),
        principal=group_principal("shared", "issuer"),
        permissions=set(),
        recursive=recursive,
    )
    await policies.add_grant(grant)
    with pytest.raises(GroupInUse):
        await management.delete_group("shared")
    assert await policies.list_grants(grant.node_id) == [grant]
    await policies.remove_grant(grant.node_id, grant.principal)
    assert tuple(group.group_id for group in await management.list_groups()) == (
        "shared",
    )
    await management.delete_group("shared")
    await policies.add_grant(grant)
    assert tuple(group.group_id for group in await management.list_groups()) == (
        "shared",
    )


@pytest.mark.asyncio
async def test_same_group_across_issuers_shares_registration_not_grants(
    database: Database,
) -> None:
    policies = DatabaseAccessControl(database)
    node_id = uuid4()
    grants = [
        AccessGrant(
            node_id=node_id,
            principal=group_principal("shared", issuer),
            permissions=set(),
            recursive=False,
        )
        for issuer in ("first", "second")
    ]
    for grant in grants:
        await policies.add_grant(grant)
    assert tuple(
        group.group_id
        for group in await create_group_management(database).list_groups()
    ) == ("shared",)
    await policies.remove_grant(node_id, grants[0].principal)
    with pytest.raises(GroupInUse):
        await create_group_management(database).delete_group("shared")
    assert await policies.list_grants(node_id) == [grants[1]]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "principal_type", [PrincipalType.USER, PrincipalType.SYSTEM, PrincipalType.GROUP]
)
async def test_ownership_registers_only_group_and_blocks_deletion(
    database: Database, principal_type: PrincipalType
) -> None:
    owner = Ownership(
        node_id=uuid4(),
        owner=Principal(type=principal_type, issuer="issuer", id="owner"),
    )
    await DatabaseAccessControl(database).set_owner(owner)
    management = create_group_management(database)
    if principal_type == PrincipalType.GROUP:
        assert tuple(group.group_id for group in await management.list_groups()) == (
            "owner",
        )
        with pytest.raises(GroupInUse):
            await management.delete_group("owner")
    else:
        assert await management.list_groups() == ()
        await management.delete_group("owner")


@pytest.mark.asyncio
async def test_grant_registration_rolls_back_with_transaction(
    database: Database,
) -> None:
    grant = AccessGrant(
        node_id=uuid4(),
        principal=group_principal("rollback", "issuer"),
        permissions=set(),
        recursive=False,
    )
    with pytest.raises(RuntimeError):
        async with database.session(mode=TransactionMode.SERIALIZED_WRITE) as session:
            await SessionAccessControl(session).add_grant(grant)
            raise RuntimeError("abort")
    assert await create_group_management(database).list_groups() == ()
    assert await DatabaseAccessControl(database).list_grants(grant.node_id) == []


@pytest.mark.asyncio
@pytest.mark.parametrize("capability", [False, True])
async def test_connector_permissions_guard_shared_deletion(
    database: Database, capability: bool
) -> None:
    store = await create_group_permission_store(database)
    await store.save_group_permissions(
        SaveGroupPermissionsRequest(
            group_id="connector",
            connector_ids=() if capability else ("orphan",),
            capabilities=(
                ConnectorCapabilityRef(
                    connector_id="orphan", capability_kind="tool", capability_key="tool"
                ),
            )
            if capability
            else (),
        )
    )
    with pytest.raises(GroupInUse):
        await create_group_management(database).delete_group("connector")
    with pytest.raises(GroupInUse):
        await store.delete_group("connector")
    await store.save_group_permissions(
        SaveGroupPermissionsRequest(
            group_id="connector", connector_ids=(), capabilities=()
        )
    )
    await store.delete_group("connector")
    assert await store.list_group_identifiers() == ()


@pytest.mark.asyncio
async def test_prepared_database_does_not_add_startup_groups_or_grants(
    database: Database,
) -> None:
    assert await create_group_management(database).list_groups() == ()
    assert await DatabaseAccessControl(database).list_grants(uuid4()) == []


@pytest.mark.asyncio
async def test_grant_first_serializes_delete_and_rejects_it(database: Database) -> None:
    management = create_group_management(database)
    grant = AccessGrant(
        node_id=uuid4(),
        principal=group_principal("racing", "issuer"),
        permissions=set(),
        recursive=False,
    )
    started = Event()

    async def delete_after_grant_started() -> None:
        started.set()
        await management.delete_group("racing")

    async with database.session(mode=TransactionMode.SERIALIZED_WRITE) as session:
        await SessionAccessControl(session).add_grant(grant)
        deletion = create_task(delete_after_grant_started())
        await started.wait()
    with pytest.raises(GroupInUse):
        await wait_for(deletion, 5)
    assert tuple(group.group_id for group in await management.list_groups()) == (
        "racing",
    )


@pytest.mark.asyncio
async def test_delete_first_serializes_grant_and_later_grant_registers_again(
    database: Database,
) -> None:
    catalogue = DatabaseGroupCatalogue(database, shared_group_usage)
    management = GroupManagementService(catalogue)
    await management.register_group(RegisterGroup(group_id="racing"))
    grant = AccessGrant(
        node_id=uuid4(),
        principal=group_principal("racing", "issuer"),
        permissions=set(),
        recursive=False,
    )
    started = Event()

    async def grant_after_delete_started() -> None:
        started.set()
        await DatabaseAccessControl(database).add_grant(grant)

    async with catalogue.write() as session:
        assert not await session.is_in_use("racing")
        await session.delete("racing")
        granting = create_task(grant_after_delete_started())
        await started.wait()
    await wait_for(granting, 5)
    assert tuple(group.group_id for group in await management.list_groups()) == (
        "racing",
    )
    assert await DatabaseAccessControl(database).list_grants(grant.node_id) == [grant]


@pytest.mark.asyncio
@pytest.mark.parametrize("principal_type", [PrincipalType.USER, PrincipalType.SYSTEM])
async def test_non_group_grants_do_not_register_groups(
    database: Database, principal_type: PrincipalType
) -> None:
    grant = AccessGrant(
        node_id=uuid4(),
        principal=Principal(type=principal_type, issuer="issuer", id="not-a-group"),
        permissions=set(),
        recursive=False,
    )
    await DatabaseAccessControl(database).add_grant(grant)
    assert await create_group_management(database).list_groups() == ()


def test_legacy_table_reexport_is_the_same_object() -> None:
    from umbod.core.groups.stores.schema import GROUP_TABLE
    from umbod.core.permissions.stores.schema import GROUP_TABLE as LEGACY_GROUP_TABLE

    assert GROUP_TABLE is LEGACY_GROUP_TABLE
