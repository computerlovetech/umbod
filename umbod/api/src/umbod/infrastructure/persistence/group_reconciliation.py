from umbod.core.persistence import (
    Database,
    TransactionMode,
    Query,
    NoFilter,
    Unordered,
    AllFields,
)
from umbod.core.groups.stores.registration import register_group_in_session
from umbod.core.permissions.stores.schema import (
    CONNECTOR_PERMISSION_TABLE,
    CONNECTOR_PERMISSION_GROUP_ID_PROJECTION,
    CAPABILITY_PERMISSION_TABLE,
    CAPABILITY_PERMISSION_GROUP_ID_PROJECTION,
)
from umbod.core.filesystem.stores.schema import GRANT_TABLE, OWNER_TABLE
from umbod.core.filesystem.models import PrincipalType


async def reconcile_group_catalogue(database: Database) -> None:
    async with database.session(mode=TransactionMode.SERIALIZED_WRITE) as session:
        connector_rows = await session.find_many(
            CONNECTOR_PERMISSION_TABLE,
            Query(NoFilter(), CONNECTOR_PERMISSION_GROUP_ID_PROJECTION, Unordered()),
        )
        capability_rows = await session.find_many(
            CAPABILITY_PERMISSION_TABLE,
            Query(NoFilter(), CAPABILITY_PERMISSION_GROUP_ID_PROJECTION, Unordered()),
        )
        grants = await session.find_many(
            GRANT_TABLE, Query(NoFilter(), AllFields(), Unordered())
        )
        owners = await session.find_many(
            OWNER_TABLE, Query(NoFilter(), AllFields(), Unordered())
        )
        group_ids = {row.group_id for row in (*connector_rows, *capability_rows)}
        group_ids.update(
            row.principal_id
            for row in grants
            if row.principal_type == PrincipalType.GROUP.value
        )
        group_ids.update(
            row.payload.owner.id
            for row in owners
            if row.payload.owner.type == PrincipalType.GROUP
        )
        for group_id in sorted(group_ids):
            await register_group_in_session(session, group_id)
