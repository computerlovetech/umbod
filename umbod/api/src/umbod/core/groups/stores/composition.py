from umbod.core.persistence import Database, DatabaseSession
from umbod.core.groups.ports import GroupUsage
from umbod.core.groups.service import GroupManagementService
from umbod.core.filesystem.stores.group_usage import FilesystemGroupUsage
from umbod.core.permissions.stores.group_usage import PermissionGroupUsage
from .service import DatabaseGroupCatalogue


class SharedGroupUsage:
    def __init__(self, usages: tuple[GroupUsage, ...]) -> None:
        self._usages = usages

    async def is_in_use(self, group_id: str) -> bool:
        for usage in self._usages:
            if await usage.is_in_use(group_id):
                return True
        return False


def shared_group_usage(session: DatabaseSession) -> GroupUsage:
    return SharedGroupUsage(
        (PermissionGroupUsage(session), FilesystemGroupUsage(session))
    )


def create_group_management(database: Database) -> GroupManagementService:
    return GroupManagementService(DatabaseGroupCatalogue(database, shared_group_usage))
