from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from pydantic import ValidationError

from umbod.core.persistence import (
    AllFields, Database, DatabaseSession, Equals, PersistenceDecodingError, Query,
    TransactionMode, Unordered,
)
from ..administration import RootPolicySession, RootPolicyState
from ..models import SYSTEM_ROOT_OWNER, AccessGrant, Ownership, Principal
from ..namespace import ROOT_ID
from .access_control import SessionAccessControl
from .namespace import SessionNamespace
from .schema import (
    GRANT_NODE, GRANT_TABLE, NODE_ID, NODE_KEY_PROJECTION, NODE_PARENT,
    NODE_TABLE, OWNER_NODE, OWNER_TABLE,
)
from .session import storage_session


class DatabaseRootPolicySession:
    def __init__(self, session: DatabaseSession) -> None:
        self._session = session
        self._namespace = SessionNamespace(session)
        self._policies = SessionAccessControl(session)

    async def observe(self) -> RootPolicyState:
        malformed = False
        try:
            nodes = await self._session.find_many(
                NODE_TABLE, Query(filter=Equals(NODE_ID, str(ROOT_ID)), projection=AllFields(), ordering=Unordered()),
            )
        except (ValidationError, PersistenceDecodingError):
            nodes = []
            malformed = True
        owners = await self._session.find_many(
            OWNER_TABLE, Query(filter=Equals(OWNER_NODE, str(ROOT_ID)), projection=AllFields(), ordering=Unordered()),
        )
        grants = await self._session.find_many(
            GRANT_TABLE, Query(filter=Equals(GRANT_NODE, str(ROOT_ID)), projection=AllFields(), ordering=Unordered()),
        )
        child = await self._session.find_one(
            NODE_TABLE, Query(
                filter=Equals(NODE_PARENT, str(ROOT_ID)),
                projection=NODE_KEY_PROJECTION, ordering=Unordered(),
            ),
        )
        return RootPolicyState(
            roots=tuple(node.payload for node in nodes if node.node_id == str(ROOT_ID)),
            owners=tuple(owner.payload for owner in owners if owner.node_id == str(ROOT_ID)),
            grants=tuple(grant.payload for grant in grants if grant.node_id == str(ROOT_ID)),
            has_children=child is not None,
            malformed_root=malformed,
        )

    async def ensure_root(self) -> None:
        await self._namespace.initialize_root()
        await self._policies.set_owner(Ownership(node_id=ROOT_ID, owner=SYSTEM_ROOT_OWNER))

    async def remove_group(self, principal: Principal) -> None:
        await self._policies.remove_grant(ROOT_ID, principal)

    async def add_group(self, grant: AccessGrant) -> None:
        await self._policies.add_grant(grant)


class DatabaseRootPolicyTransactions:
    def __init__(self, database: Database) -> None:
        self._database = database

    @asynccontextmanager
    async def read(self) -> AsyncIterator[RootPolicySession]:
        async with storage_session(self._database, TransactionMode.READ_WRITE) as session:
            yield DatabaseRootPolicySession(session)

    @asynccontextmanager
    async def write(self) -> AsyncIterator[RootPolicySession]:
        async with storage_session(self._database, TransactionMode.SERIALIZED_WRITE) as session:
            yield DatabaseRootPolicySession(session)
