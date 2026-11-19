from umbod.core.groups.stores.registration import register_group_in_session
from umbod.core.persistence import (
    AllFields,
    AllOf,
    Database,
    DatabaseSession,
    DeleteQuery,
    Equals,
    OneOf,
    Query,
    ReadSession,
    PersistenceDecodingError,
    TransactionMode,
    Unordered,
    UpsertCommand,
)
from ..namespaces.models import NamespacePolicy
from ..errors import OwnershipNotFound, PolicyDecodingFailure
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
from .discovery_events import append_discovery_changed


def grant_key(node_id: NodeId, principal: Principal) -> GrantKey:
    return GrantKey(
        node_id=str(node_id),
        principal_type=principal.type.value,
        issuer=principal.issuer,
        principal_id=principal.id,
    )


async def granted_node_ids(
    session: ReadSession, principals: frozenset[Principal],
) -> frozenset[NodeId]:
    by_authority: dict[tuple[PrincipalType, str], set[str]] = {}
    for principal in principals:
        by_authority.setdefault((principal.type, principal.issuer), set()).add(principal.id)

    node_ids: set[NodeId] = set()
    try:
        for (principal_type, issuer), principal_ids in by_authority.items():
            ids = sorted(principal_ids)
            for offset in range(0, len(ids), 200):
                rows = await session.find_many(
                    GRANT_TABLE,
                    Query(
                        filter=AllOf((
                            Equals(GRANT_TYPE, principal_type.value),
                            Equals(GRANT_ISSUER, issuer),
                            OneOf(GRANT_PRINCIPAL, tuple(ids[offset:offset + 200])),
                        )),
                        projection=AllFields(),
                        ordering=Unordered(),
                    ),
                )
                node_ids.update(row.payload.node_id for row in rows)
    except PersistenceDecodingError as error:
        raise PolicyDecodingFailure("Stored filesystem policy cannot be decoded") from error
    return frozenset(node_ids)


class DatabaseAccessControl:
    def __init__(self, database: Database) -> None:
        self._database = database

    async def list_namespace_policies(self) -> list[NamespacePolicy]:
        async with self._database.read_session() as session:
            from .namespaces import namespace_policies
            return await namespace_policies(session)

    async def get_owner(self, node_id: NodeId) -> Ownership:
        async with storage_session(self._database, TransactionMode.READ_WRITE) as session:
            return await SessionAccessControl(session).get_owner(node_id)

    async def set_owner(self, ownership: Ownership) -> None:
        async with storage_session(self._database, TransactionMode.SERIALIZED_WRITE) as session:
            return await SessionAccessControl(session).set_owner(ownership)

    async def list_grants(self, node_id: NodeId) -> list[AccessGrant]:
        async with storage_session(self._database, TransactionMode.READ_WRITE) as session:
            return await SessionAccessControl(session).list_grants(node_id)

    async def list_granted_node_ids(self, principals: frozenset[Principal]) -> frozenset[NodeId]:
        async with self._database.read_session() as session:
            return await granted_node_ids(session, principals)

    async def add_grant(self, grant: AccessGrant) -> None:
        async with storage_session(self._database, TransactionMode.SERIALIZED_WRITE) as session:
            return await SessionAccessControl(session).add_grant(grant)

    async def remove_grant(self, node_id: NodeId, principal: Principal) -> None:
        async with storage_session(self._database, TransactionMode.SERIALIZED_WRITE) as session:
            return await SessionAccessControl(session).remove_grant(node_id, principal)

    async def clear_node(self, node_id: NodeId) -> None:
        async with storage_session(self._database, TransactionMode.SERIALIZED_WRITE) as session:
            await SessionAccessControl(session).clear_node(node_id)


class SessionAccessReader:
    def __init__(self, session: ReadSession) -> None:
        self._reader = session

    async def list_namespace_policies(self) -> list[NamespacePolicy]:
        from .namespaces import namespace_policies
        return await namespace_policies(self._reader)

    async def get_owner(self, node_id: NodeId) -> Ownership:
        record = await self._reader.find_one(
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

    async def list_grants(self, node_id: NodeId) -> list[AccessGrant]:
        try:
            records = await self._reader.find_many(
                GRANT_TABLE,
                Query(
                    filter=Equals(GRANT_NODE, str(node_id)),
                    projection=AllFields(),
                    ordering=Unordered(),
                ),
            )
        except PersistenceDecodingError as error:
            raise PolicyDecodingFailure("Stored filesystem policy cannot be decoded") from error
        return [record.payload.model_copy(deep=True) for record in records]

    async def list_granted_node_ids(self, principals: frozenset[Principal]) -> frozenset[NodeId]:
        return await granted_node_ids(self._reader, principals)


class SessionAccessControl(SessionAccessReader):
    def __init__(self, session: DatabaseSession) -> None:
        super().__init__(session)
        self._session = session

    async def clear_node(self, node_id: NodeId) -> None:
        await self._session.delete(GRANT_TABLE, DeleteQuery(filter=Equals(GRANT_NODE, str(node_id))))
        await self._session.delete(OWNER_TABLE, DeleteQuery(filter=Equals(OWNER_NODE, str(node_id))))
        await append_discovery_changed(self._session)

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

        await append_discovery_changed(self._session)

    async def add_grant(self, grant: AccessGrant) -> None:
        if grant.principal.type == PrincipalType.GROUP:
            await register_group_in_session(self._session, grant.principal.id)
        await self.upsert_registered_grant(grant)

    async def upsert_registered_grant(self, grant: AccessGrant) -> None:
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

        await append_discovery_changed(self._session)

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
        await append_discovery_changed(self._session)
