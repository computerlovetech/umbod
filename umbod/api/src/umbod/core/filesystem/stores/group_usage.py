from umbod.core.persistence import (
    DatabaseSession,
    Query,
    NoFilter,
    Unordered,
    AllFields,
    Equals,
    AllOf,
)
from ..models import PrincipalType
from .schema import GRANT_TABLE, GRANT_TYPE, GRANT_PRINCIPAL, OWNER_TABLE


class FilesystemGroupUsage:
    def __init__(self, session: DatabaseSession) -> None:
        self._session = session

    async def is_in_use(self, group_id: str) -> bool:
        grant = await self._session.find_one(
            GRANT_TABLE,
            Query(
                AllOf(
                    (
                        Equals(GRANT_TYPE, PrincipalType.GROUP.value),
                        Equals(GRANT_PRINCIPAL, group_id),
                    )
                ),
                AllFields(),
                Unordered(),
            ),
        )
        if grant is not None:
            return True
        owners = await self._session.find_many(
            OWNER_TABLE, Query(NoFilter(), AllFields(), Unordered())
        )
        return any(
            row.payload.owner.type == PrincipalType.GROUP
            and row.payload.owner.id == group_id
            for row in owners
        )
