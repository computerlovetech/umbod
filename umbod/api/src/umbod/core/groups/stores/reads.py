from umbod.core.persistence import ReadSession
from umbod.core.persistence.plan import ManyRead, ReadPlanOperations
from umbod.core.persistence.query import NoFilter, Query, Unordered

from .schema import GROUP_ID_PROJECTION, GROUP_TABLE, GroupIdResult


_GROUP_IDS = Query(
    filter=NoFilter(), projection=GROUP_ID_PROJECTION, ordering=Unordered()
)


def plan_group_inventory_read(plan: ReadPlanOperations) -> ManyRead[GroupIdResult]:
    return plan.find_many(GROUP_TABLE, _GROUP_IDS)


async def read_registered_group_ids(session: ReadSession) -> frozenset[str]:
    records = await session.find_many(GROUP_TABLE, _GROUP_IDS)
    return frozenset(record.group_id for record in records)
