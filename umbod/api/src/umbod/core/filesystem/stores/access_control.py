from umbod.core.groups.stores.registration import register_group_in_session
from umbod.core.persistence import (
    AllFields,
    AllOf,
    Database,
    DatabaseSession,
    DeleteQuery,
    Equals,
    Query,
    TransactionMode,
    Unordered,
    UpsertCommand,
)
from ..errors import OwnershipNotFound
from ..models import AccessGrant, NodeId, Ownership, Principal, PrincipalType
from .schema import (
    GRANT_ISSUER,
    GRANT_NODE,
    GRANT_PRINCIPAL,
    GRANT_TABLE,
    GRANT_TYPE,
    OWNER_NODE,
    OWNER_TABLE,
    GrantKey,
    GrantRecord,
    NodeKey,
    OwnershipRecord,
)
from .session import storage_session


def grant_key(node_id: NodeId, principal: Principal) -> GrantKey:
    return GrantKey(
        node_id=str(node_id),
        principal_type=principal.type.value,
        issuer=principal.issuer,
        principal_id=principal.id,
    )


class DatabaseAccessControl:
    def __init__(self, database: Database) -> None:
        self._database = database

    async def get_owner(self, node_id: NodeId) -> Ownership:
        async with storage_session(self._database, TransactionMode.READ_WRITE) as session:
            return await SessionAccessControl(session).get_owner(node_id)

    async def set_owner(self, ownership: Ownership) -> None:
        async with storage_session(self._database, TransactionMode.SERIALIZED_WRITE) as session:
            return await SessionAccessControl(session).set_owner(ownership)

    async def list_grants(self, node_id: NodeId) -> list[AccessGrant]:
        async with storage_session(self._database, TransactionMode.READ_WRITE) as session:
            return await SessionAccessControl(session).list_grants(node_id)

    async def add_grant(self, grant: AccessGrant) -> None:
        async with storage_session(self._database, TransactionMode.SERIALIZED_WRITE) as session:
            return await SessionAccessControl(session).add_grant(grant)

    async def remove_grant(self, node_id: NodeId, principal: Principal) -> None:
        async with storage_session(self._database, TransactionMode.SERIALIZED_WRITE) as session:
            return await SessionAccessControl(session).remove_grant(node_id, principal)


class SessionAccessControl:
    def __init__(self, session: DatabaseSession) -> None:
        self._session = session

    async def get_owner(self, node_id: NodeId) -> Ownership:
        record = await self._session.find_one(
            OWNER_TABLE,
            Query(
                filter=Equals(OWNER_NODE, str(node_id)),
                projection=AllFields(),
                ordering=Unordered(),
            ),
        )
        if record is None:
            raise OwnershipNotFound(str(node_id))
        return record.payload.model_copy(deep=True)

    async def set_owner(self, ownership: Ownership) -> None:
        if ownership.owner.type == PrincipalType.GROUP:
            await register_group_in_session(self._session, ownership.owner.id)
        key = NodeKey(node_id=str(ownership.node_id))
        await self._session.upsert(
            OWNER_TABLE,
            UpsertCommand(
                key=key,
                row=OwnershipRecord(
                    node_id=key.node_id, payload=ownership.model_copy(deep=True)
                ),
            ),
        )

    async def list_grants(self, node_id: NodeId) -> list[AccessGrant]:
        records = await self._session.find_many(
            GRANT_TABLE,
            Query(
                filter=Equals(GRANT_NODE, str(node_id)),
                projection=AllFields(),
                ordering=Unordered(),
            ),
        )
        return [record.payload.model_copy(deep=True) for record in records]

    async def add_grant(self, grant: AccessGrant) -> None:
        if grant.principal.type == PrincipalType.GROUP:
            await register_group_in_session(self._session, grant.principal.id)
        key = grant_key(grant.node_id, grant.principal)
        await self._session.upsert(
            GRANT_TABLE,
            UpsertCommand(
                key=key,
                row=GrantRecord(
                    **key.model_dump(), payload=grant.model_copy(deep=True)
                ),
            ),
        )

    async def remove_grant(self, node_id: NodeId, principal: Principal) -> None:
        key = grant_key(node_id, principal)
        await self._session.delete(
            GRANT_TABLE,
            DeleteQuery(
                filter=AllOf(
                    (
                        Equals(GRANT_NODE, key.node_id),
                        Equals(GRANT_TYPE, key.principal_type),
                        Equals(GRANT_ISSUER, key.issuer),
                        Equals(GRANT_PRINCIPAL, key.principal_id),
                    )
                )
            ),
        )
