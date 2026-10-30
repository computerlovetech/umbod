from collections.abc import AsyncIterator
from pathlib import Path
from uuid import uuid4

import pytest
import pytest_asyncio

from tests.persistence_runtime import prepared_inmemory_runtime, prepared_sqlite_runtime
from umbod.core.persistence import Database, InsertCommand, TransactionMode
from umbod.core.groups import UpdateGroupMetadata
from umbod.core.groups.stores.composition import create_group_management
from umbod.core.filesystem.models import (
    AccessGrant,
    Ownership,
    Principal,
    PrincipalType,
)
from umbod.core.filesystem.stores.access_control import DatabaseAccessControl
from umbod.core.filesystem.stores.schema import (
    GRANT_TABLE,
    OWNER_TABLE,
    GrantRecord,
    OwnershipRecord,
)
from umbod.core.permissions.domain import SaveGroupPermissionsRequest
from umbod.core.permissions.factories import create_group_permission_store
from umbod.core.permissions.stores.schema import (
    CAPABILITY_PERMISSION_TABLE,
    CONNECTOR_PERMISSION_TABLE,
    GroupCapabilityPermissionRecord,
    GroupConnectorPermissionRecord,
)
from umbod.infrastructure.persistence.group_reconciliation import (
    reconcile_group_catalogue,
)


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


def group_principal(group_id: str, issuer: str) -> Principal:
    return Principal(type=PrincipalType.GROUP, issuer=issuer, id=group_id)


@pytest.mark.asyncio
async def test_reconciliation_preserves_legacy_identities_and_all_policy_rows(
    database: Database,
) -> None:
    grant = AccessGrant(
        node_id=uuid4(),
        principal=group_principal(" ", ""),
        permissions=set(),
        recursive=True,
    )
    owner = Ownership(node_id=uuid4(), owner=group_principal("owner", "other"))
    async with database.session(mode=TransactionMode.SERIALIZED_WRITE) as session:
        await session.insert(
            CONNECTOR_PERMISSION_TABLE,
            InsertCommand(
                row=GroupConnectorPermissionRecord(group_id="", connector_id="legacy")
            ),
        )
        await session.insert(
            CAPABILITY_PERMISSION_TABLE,
            InsertCommand(
                row=GroupCapabilityPermissionRecord(
                    group_id=" Mixed ",
                    connector_id="legacy",
                    capability_kind="tool",
                    capability_key="key",
                )
            ),
        )
        await session.insert(
            GRANT_TABLE,
            InsertCommand(
                row=GrantRecord(
                    node_id=str(grant.node_id),
                    principal_type="group",
                    issuer="",
                    principal_id=" ",
                    payload=grant,
                )
            ),
        )
        await session.insert(
            OWNER_TABLE,
            InsertCommand(
                row=OwnershipRecord(node_id=str(owner.node_id), payload=owner)
            ),
        )
    assert await create_group_management(database).list_groups() == ()
    await reconcile_group_catalogue(database)
    await reconcile_group_catalogue(database)
    assert tuple(
        group.group_id
        for group in await create_group_management(database).list_groups()
    ) == ("", " ", " Mixed ", "owner")
    policies = DatabaseAccessControl(database)
    assert await policies.list_grants(grant.node_id) == [grant]
    assert await policies.get_owner(owner.node_id) == owner
    store = await create_group_permission_store(database)
    assert (await store.list_group_permissions("")).connector_ids == ("legacy",)
    assert len((await store.list_group_permissions(" Mixed ")).capabilities) == 1
    management = create_group_management(database)
    updated = await management.update_group_metadata(" Mixed ", UpdateGroupMetadata(label="Edited", description="Preserved", expected_revision=1))
    await reconcile_group_catalogue(database)
    assert updated in await management.list_groups()
    await store.save_group_permissions(
        SaveGroupPermissionsRequest(
            group_id=" Mixed ", connector_ids=("legacy",), capabilities=()
        )
    )
    assert updated in await management.list_groups()
