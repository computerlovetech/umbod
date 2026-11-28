from collections.abc import Callable
from hmac import compare_digest

from umbod.core.groups.stores.reads import read_group_instance
from umbod.core.persistence import (
    AllFields,
    Database,
    Equals,
    InsertCommand,
    NoFilter,
    Query,
    ReadSession,
    TransactionMode,
    Unordered,
    UpsertCommand,
)

from .errors import AgentGroupNotFound
from .models import (
    AgentCredentialMetadata,
    AgentCredentialStatus,
    StoredAgentCredential,
)
from .schema import (
    AGENT_CREDENTIAL_TABLE,
    AGENT_ID,
    AgentCredentialKey,
    AgentCredentialRow,
)


def _row(record: StoredAgentCredential) -> AgentCredentialRow:
    return AgentCredentialRow(
        agent_id=record.metadata.agent_id,
        metadata=record.metadata,
        group_instance_id=record.group_instance_id,
        digest=record.digest,
    )


async def _find_row(session: ReadSession, agent_id: str) -> AgentCredentialRow | None:
    return await session.find_one(
        AGENT_CREDENTIAL_TABLE,
        Query(Equals(AGENT_ID, agent_id), AllFields(), Unordered()),
    )


async def _require_current_group(
    session: ReadSession, record: StoredAgentCredential
) -> None:
    group = await read_group_instance(session, record.metadata.group_id)
    if group is None or group.instance_id != record.group_instance_id:
        raise AgentGroupNotFound("Agent group instance no longer exists")


class DatabaseAgentCredentialStore:
    def __init__(self, database: Database) -> None:
        self._database = database

    async def insert(self, record: StoredAgentCredential) -> bool:
        async with self._database.session(
            mode=TransactionMode.SERIALIZED_WRITE
        ) as session:
            await _require_current_group(session, record)
            return await session.insert(
                AGENT_CREDENTIAL_TABLE, InsertCommand(row=_row(record))
            )

    async def find(self, agent_id: str) -> StoredAgentCredential | None:
        async with self._database.read_session() as session:
            row = await _find_row(session, agent_id)
        if row is None:
            return None
        return StoredAgentCredential(
            metadata=row.metadata,
            group_instance_id=row.group_instance_id,
            digest=row.digest,
        )

    async def list_agents(self) -> tuple[AgentCredentialMetadata, ...]:
        async with self._database.read_session() as session:
            rows = await session.find_many(
                AGENT_CREDENTIAL_TABLE, Query(NoFilter(), AllFields(), Unordered())
            )
        return tuple(row.metadata for row in sorted(rows, key=lambda row: row.agent_id))

    async def compare_and_replace(
        self,
        previous: StoredAgentCredential,
        build_replacement: Callable[[], StoredAgentCredential],
    ) -> bool:
        agent_id = previous.metadata.agent_id
        async with self._database.session(
            mode=TransactionMode.SERIALIZED_WRITE
        ) as session:
            current = await _find_row(session, agent_id)
            if (
                current is None
                or current.metadata != previous.metadata
                or current.group_instance_id != previous.group_instance_id
            ):
                return False
            if not compare_digest(current.digest, previous.digest):
                return False
            replacement = build_replacement()
            if (
                replacement.metadata.agent_id != agent_id
                or replacement.metadata.group_id != previous.metadata.group_id
                or replacement.group_instance_id != previous.group_instance_id
            ):
                raise ValueError("Cannot change the agent or its group binding")
            if replacement.metadata.status is AgentCredentialStatus.ACTIVE:
                await _require_current_group(session, replacement)
            await session.upsert(
                AGENT_CREDENTIAL_TABLE,
                UpsertCommand(
                    key=AgentCredentialKey(agent_id=agent_id), row=_row(replacement)
                ),
            )
        return True
