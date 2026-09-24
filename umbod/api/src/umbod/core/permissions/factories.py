from umbod.core.permissions import GroupPermissionStore
from umbod.core.permissions.stores.schema import (
    CAPABILITY_PERMISSION_TABLE,
    CONNECTOR_PERMISSION_TABLE,
    GROUP_TABLE,
)
from umbod.core.permissions.stores.service import GroupPermissionStoreService
from umbod.core.persistence import Database


async def create_group_permission_store(database: Database) -> GroupPermissionStore:
    return GroupPermissionStoreService(
        database, GROUP_TABLE, CONNECTOR_PERMISSION_TABLE, CAPABILITY_PERMISSION_TABLE
    )
