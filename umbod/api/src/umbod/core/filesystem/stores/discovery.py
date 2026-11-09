from umbod.core.persistence import AllFields, Database, NoFilter, Query, Unordered

from ..authorization.discovery import (
    AuthorizationGrant,
    AuthorizationNode,
    FilesystemAuthorizationSnapshot,
)
from .schema import GRANT_TABLE, NODE_TABLE, OWNER_TABLE


class DatabaseFilesystemAuthorizationReader:
    def __init__(self, database: Database) -> None:
        self._database = database

    async def read(self) -> FilesystemAuthorizationSnapshot:
        async with self._database.read_session() as session:
            nodes = await session.find_many(
                NODE_TABLE,
                Query(filter=NoFilter(), projection=AllFields(), ordering=Unordered()),
            )
            owners = await session.find_many(
                OWNER_TABLE,
                Query(filter=NoFilter(), projection=AllFields(), ordering=Unordered()),
            )
            grants = await session.find_many(
                GRANT_TABLE,
                Query(filter=NoFilter(), projection=AllFields(), ordering=Unordered()),
            )
            return FilesystemAuthorizationSnapshot(
                nodes=tuple(
                    AuthorizationNode(node_id=node.payload.id, kind=node.payload.kind, parent_id=node.payload.parent_id)
                    for node in nodes
                ),
                ownerships=tuple(owner.payload for owner in owners),
                grants=tuple(
                    AuthorizationGrant.model_validate(grant.payload.model_dump())
                    for grant in grants
                ),
            )
