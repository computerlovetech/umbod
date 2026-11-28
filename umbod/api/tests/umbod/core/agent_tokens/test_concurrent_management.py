import asyncio
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from datetime import timedelta
from typing import Literal

import pytest

from umbod.core.administrator.connector_configuration import AdministratorPrincipal
from umbod.core.administrator.operations import AdministratorAccess
from umbod.core.agent_tokens import (
    AgentCredentialConflict,
    AgentCredentialService,
    AgentCredentialStatus,
    AgentGroupNotFound,
    CreateAgent,
    InvalidAgentCredential,
    IssuedAgentCredential,
    RotateAgentCredential,
    SecureAgentCredentialGenerator,
)
from umbod.core.agent_tokens.models import StoredAgentCredential
from umbod.core.agent_tokens.store import DatabaseAgentCredentialStore
from umbod.core.groups import (
    GroupInstance,
    GroupInstanceLookup,
    GroupManagementService,
    RegisterGroup,
)
from umbod.core.persistence import Database, DatabaseSession, TransactionMode

from .conftest import MutableClock, MutableGroups

pytestmark = pytest.mark.asyncio


class PausedFirstReplacementStore(DatabaseAgentCredentialStore):
    def __init__(self, database: Database) -> None:
        super().__init__(database)
        self.waiting = asyncio.Event()
        self.resume = asyncio.Event()

    async def compare_and_replace(
        self,
        previous: StoredAgentCredential,
        build_replacement: Callable[[], StoredAgentCredential],
    ) -> bool:
        if not self.waiting.is_set():
            self.waiting.set()
            await self.resume.wait()
        return await super().compare_and_replace(previous, build_replacement)


class PausedGroupLookup:
    def __init__(self, lookup: GroupInstanceLookup) -> None:
        self._lookup = lookup
        self.waiting = asyncio.Event()
        self.resume = asyncio.Event()

    async def find_group_instance(self, group_id: str) -> GroupInstance | None:
        snapshot = await self._lookup.find_group_instance(group_id)
        self.waiting.set()
        await self.resume.wait()
        return snapshot


class CommitRejected(RuntimeError):
    pass


def _reject_commits(database: Database, monkeypatch: pytest.MonkeyPatch) -> None:
    session_factory = database.session

    @asynccontextmanager
    async def session_without_commit(
        *, mode: TransactionMode
    ) -> AsyncIterator[DatabaseSession]:
        async with session_factory(mode=mode) as session:
            yield session
            raise CommitRejected()

    monkeypatch.setattr(database, "session", session_without_commit)


Mutation = Literal["rotate", "revoke"]


async def _mutate(
    service: AgentCredentialService,
    principal: AdministratorPrincipal,
    request: RotateAgentCredential,
    mutation: Mutation,
) -> IssuedAgentCredential | bool:
    if mutation == "rotate":
        return await service.rotate(principal, request)
    return await service.revoke(principal, request.agent_id)


@pytest.mark.parametrize(
    "first,winner", [("rotate", "rotate"), ("revoke", "rotate"), ("rotate", "revoke")]
)
async def test_stale_management_cannot_replace_the_winning_credential_state(
    database: Database,
    access: AdministratorAccess,
    administrator: AdministratorPrincipal,
    groups: MutableGroups,
    clock: MutableClock,
    create_request: CreateAgent,
    first: Mutation,
    winner: Mutation,
) -> None:
    store = PausedFirstReplacementStore(database)
    service = AgentCredentialService(
        access, groups, store, clock, SecureAgentCredentialGenerator()
    )
    issued = await service.create(administrator, create_request)
    request = RotateAgentCredential(
        agent_id=issued.metadata.agent_id,
        expires_at=create_request.expires_at + timedelta(days=1),
    )

    pending = asyncio.create_task(_mutate(service, administrator, request, first))
    try:
        await asyncio.wait_for(store.waiting.wait(), timeout=3)
        winning_result = await _mutate(service, administrator, request, winner)
    finally:
        store.resume.set()
        with pytest.raises(AgentCredentialConflict, match="changed concurrently"):
            await pending

    with pytest.raises(InvalidAgentCredential):
        await service.verify_for_public_mcp(issued.token)
    if isinstance(winning_result, IssuedAgentCredential):
        assert await service.list_agents(administrator) == (winning_result.metadata,)
        assert (
            await service.verify_for_public_mcp(winning_result.token)
        ).agent_id == request.agent_id
    else:
        assert winning_result is True
        assert await service.list_agents(administrator) == (
            issued.metadata.model_copy(
                update={"status": AgentCredentialStatus.REVOKED}
            ),
        )


async def test_rotation_preserves_the_bearer_when_replacement_expires_before_writing(
    database: Database,
    access: AdministratorAccess,
    administrator: AdministratorPrincipal,
    groups: MutableGroups,
    clock: MutableClock,
    create_request: CreateAgent,
) -> None:
    store = PausedFirstReplacementStore(database)
    service = AgentCredentialService(
        access, groups, store, clock, SecureAgentCredentialGenerator()
    )
    issued = await service.create(administrator, create_request)
    replacement_expiry = clock.now() + timedelta(seconds=1)
    request = RotateAgentCredential(
        agent_id=issued.metadata.agent_id, expires_at=replacement_expiry
    )

    pending = asyncio.create_task(service.rotate(administrator, request))
    try:
        await asyncio.wait_for(store.waiting.wait(), timeout=3)
        clock.instant = replacement_expiry
    finally:
        store.resume.set()
        with pytest.raises(ValueError, match="Expiry must be in the future"):
            await pending

    assert await service.list_agents(administrator) == (issued.metadata,)
    assert (
        await service.verify_for_public_mcp(issued.token)
    ).agent_id == request.agent_id


@pytest.mark.parametrize("operation", ["create", "rotate"])
async def test_stale_group_lookup_cannot_commit_issuance_for_a_replaced_group(
    service: AgentCredentialService,
    store: DatabaseAgentCredentialStore,
    access: AdministratorAccess,
    administrator: AdministratorPrincipal,
    group_management: GroupManagementService,
    groups: MutableGroups,
    clock: MutableClock,
    create_request: CreateAgent,
    issued: IssuedAgentCredential,
    operation: Literal["create", "rotate"],
) -> None:
    paused_lookup = PausedGroupLookup(groups)
    stale_service = AgentCredentialService(
        access, paused_lookup, store, clock, SecureAgentCredentialGenerator()
    )
    if operation == "create":
        mutation = stale_service.create(administrator, create_request)
    else:
        mutation = stale_service.rotate(
            administrator,
            RotateAgentCredential(
                agent_id=issued.metadata.agent_id, expires_at=create_request.expires_at
            ),
        )
    pending = asyncio.create_task(mutation)
    try:
        await asyncio.wait_for(paused_lookup.waiting.wait(), timeout=3)
        await group_management.delete_group(create_request.group_id)
        await group_management.register_group(
            RegisterGroup(group_id=create_request.group_id)
        )
    finally:
        paused_lookup.resume.set()
        with pytest.raises(AgentGroupNotFound):
            await pending

    assert await service.list_agents(administrator) == (issued.metadata,)


async def test_rotation_does_not_disclose_a_replacement_or_invalidate_the_old_bearer_on_commit_failure(
    database: Database,
    service: AgentCredentialService,
    administrator: AdministratorPrincipal,
    issued: IssuedAgentCredential,
    create_request: CreateAgent,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _reject_commits(database, monkeypatch)

    with pytest.raises(CommitRejected):
        await service.rotate(
            administrator,
            RotateAgentCredential(
                agent_id=issued.metadata.agent_id, expires_at=create_request.expires_at
            ),
        )

    assert await service.list_agents(administrator) == (issued.metadata,)
    assert (
        await service.verify_for_public_mcp(issued.token)
    ).agent_id == issued.metadata.agent_id
