from umbod.core.groups.models import GroupInstance
from umbod.core.groups.ports import GroupInstanceLookup
from umbod.core.persistence import Database, ReadSession
from umbod.core.persistence.plan import ManyRead, ReadPlanOperations
from umbod.core.persistence.query import Equals, NoFilter, Query, Unordered

from .schema import GROUP_ID, GROUP_ID_PROJECTION, GROUP_INSTANCE_PROJECTION, GROUP_TABLE, GroupIdResult


_GROUP_IDS = Query(
    filter=NoFilter(), projection=GROUP_ID_PROJECTION, ordering=Unordered()
)


def plan_group_inventory_read(plan: ReadPlanOperations) -> ManyRead[GroupIdResult]:
    return plan.find_many(GROUP_TABLE, _GROUP_IDS)


async def read_registered_group_ids(session: ReadSession) -> frozenset[str]:
    records = await session.find_many(GROUP_TABLE, _GROUP_IDS)
    return frozenset(record.group_id for record in records)


async def read_group_instance(session: ReadSession, group_id: str) -> GroupInstance | None:
    return await session.find_one(
        GROUP_TABLE, Query(Equals(GROUP_ID, group_id), GROUP_INSTANCE_PROJECTION, Unordered())
    )


class DatabaseGroupInstanceLookup(GroupInstanceLookup):
    def __init__(self, database: Database) -> None:
        self._database = database

    async def find_group_instance(self, group_id: str) -> GroupInstance | None:
        async with self._database.read_session() as session:
            return await read_group_instance(session, group_id)
