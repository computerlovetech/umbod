from umbod.core.persistence import AllFields, OneOf, Query, ReadPlan, ReadSession, Unordered

from ..authorization.discovery import AuthorizationGrant
from ..models import NodeId, Ownership
from .schema import GRANT_NODE, GRANT_TABLE, OWNER_NODE, OWNER_TABLE


async def read_scoped_acls(
    session: ReadSession, node_ids: tuple[NodeId, ...],
) -> tuple[tuple[Ownership, ...], tuple[AuthorizationGrant, ...]]:
    plan = ReadPlan()
    ids = sorted({str(value) for value in node_ids})
    owner_reads = []
    grant_reads = []
    for offset in range(0, len(ids), 200):
        batch = tuple(ids[offset:offset + 200])
        owner_reads.append(plan.find_many(
            OWNER_TABLE, Query(filter=OneOf(OWNER_NODE, batch), projection=AllFields(), ordering=Unordered()),
        ))
        grant_reads.append(plan.find_many(
            GRANT_TABLE, Query(filter=OneOf(GRANT_NODE, batch), projection=AllFields(), ordering=Unordered()),
        ))
    results = await plan.execute(session)
    return (
        tuple(row.payload for read in owner_reads for row in results.get(read)),
        tuple(AuthorizationGrant.model_validate(row.payload.model_dump()) for read in grant_reads for row in results.get(read)),
    )


