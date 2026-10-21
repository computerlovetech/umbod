from umbod.core.permissions.factories import create_group_permission_store
from umbod.core.permissions.ports import GroupPermissionReader
from umbod.core.persistence import Database


class DatabaseGroupPermissionReaderFactory:
    def __init__(self, database: Database) -> None:
        self._database = database

    async def create(self) -> GroupPermissionReader:
        return await create_group_permission_store(self._database)
