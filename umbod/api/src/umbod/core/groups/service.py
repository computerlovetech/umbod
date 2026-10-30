from .models import Group, GroupInUse, RegisterGroup, RegisterGroupMetadata, UpdateGroupMetadata
from .ports import GroupCatalogue


class GroupManagementService:
    def __init__(self, catalogue: GroupCatalogue) -> None:
        self._catalogue = catalogue

    async def list_groups(self) -> tuple[Group, ...]:
        return await self._catalogue.list_groups()

    async def register_group(self, request: RegisterGroup) -> None:
        async with self._catalogue.write() as session:
            await session.register(request.group_id)

    async def register_group_metadata(self, request: RegisterGroupMetadata) -> None:
        async with self._catalogue.write() as session:
            await session.register_metadata(request)

    async def update_group_metadata(self, group_id: str, request: UpdateGroupMetadata) -> Group:
        async with self._catalogue.write() as session:
            return await session.update_metadata(group_id, request)

    async def delete_group(self, group_id: str) -> None:
        async with self._catalogue.write() as session:
            if await session.is_in_use(group_id):
                raise GroupInUse(
                    "Remove group permissions and ownership before deleting this group."
                )
            await session.delete(group_id)
