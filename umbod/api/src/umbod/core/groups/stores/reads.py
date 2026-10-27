from umbod.core.persistence.plan import ManyRead, ReadPlanOperations
from umbod.core.persistence.query import NoFilter, Query, Unordered

from .schema import GROUP_ID_PROJECTION, GROUP_TABLE, GroupIdResult


def plan_group_inventory_read(plan: ReadPlanOperations) -> ManyRead[GroupIdResult]:
    return plan.find_many(
        GROUP_TABLE,
        Query(filter=NoFilter(), projection=GROUP_ID_PROJECTION, ordering=Unordered()),
    )
