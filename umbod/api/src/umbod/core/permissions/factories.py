from umbod.core.permissions.ports import (
    GroupInstancePermissionReader,
    GroupPermissionStore,
)
from umbod.core.permissions.stores.schema import (
    CAPABILITY_PERMISSION_TABLE,
    CONNECTOR_PERMISSION_TABLE,
)
from umbod.core.permissions.stores.service import GroupPermissionStoreService
from umbod.core.persistence import Database


async def create_group_permission_store(database: Database) -> GroupPermissionStore:
    return _create_store(database)


def create_group_instance_permission_reader(
    database: Database,
) -> GroupInstancePermissionReader:
    return _create_store(database)


def _create_store(database: Database) -> GroupPermissionStoreService:
    return GroupPermissionStoreService(
        database, CONNECTOR_PERMISSION_TABLE, CAPABILITY_PERMISSION_TABLE
    )
