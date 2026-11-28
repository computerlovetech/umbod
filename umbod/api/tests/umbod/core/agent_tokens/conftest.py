from collections.abc import AsyncIterator
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio

from tests.persistence_runtime import prepared_inmemory_runtime
from umbod.core.administrator.connector_configuration import AdministratorPrincipal
from umbod.core.administrator.operations import AdministratorAccess
from umbod.core.agent_tokens import (
    AgentCredentialService,
    CreateAgent,
    IssuedAgentCredential,
    SecureAgentCredentialGenerator,
)
from umbod.core.credential_expiry import NeverExpires
from umbod.core.agent_tokens.store import DatabaseAgentCredentialStore
from umbod.core.groups import GroupInstance, GroupInstanceLookup, GroupManagementService
from umbod.core.groups.models import RegisterGroupMetadata
from umbod.core.groups.stores.composition import create_group_management
from umbod.core.groups.stores.reads import DatabaseGroupInstanceLookup
from umbod.core.persistence import Database


class MutableClock:
    def __init__(self, instant: datetime) -> None:
        self.instant = instant

    def now(self) -> datetime:
        return self.instant


class MutableGroups:
    def __init__(self, lookup: GroupInstanceLookup) -> None:
        self._lookup = lookup
        self.available = True

    async def find_group_instance(self, group_id: str) -> GroupInstance | None:
        if not self.available:
            raise RuntimeError("Group catalogue unavailable")
        return await self._lookup.find_group_instance(group_id)


@pytest.fixture
def access() -> AdministratorAccess:
    return AdministratorAccess("administrators")


@pytest.fixture
def administrator() -> AdministratorPrincipal:
    return AdministratorPrincipal(memberships=("administrators", "human-group"))


@pytest.fixture
def clock() -> MutableClock:
    return MutableClock(datetime(2030, 1, 1, tzinfo=timezone.utc))


@pytest.fixture
def groups(database: Database) -> MutableGroups:
    return MutableGroups(DatabaseGroupInstanceLookup(database))


@pytest.fixture
def group_management(database: Database) -> GroupManagementService:
    return create_group_management(database)


@pytest_asyncio.fixture
async def database() -> AsyncIterator[Database]:
    runtime = await prepared_inmemory_runtime()
    try:
        await create_group_management(runtime.database).register_group_metadata(
            RegisterGroupMetadata(
                group_id="agent-group", label="Agent group", description=""
            )
        )
        yield runtime.database
    finally:
        await runtime.shutdown()


@pytest.fixture
def store(database: Database) -> DatabaseAgentCredentialStore:
    return DatabaseAgentCredentialStore(database)


@pytest.fixture
def service(
    access: AdministratorAccess,
    groups: MutableGroups,
    store: DatabaseAgentCredentialStore,
    clock: MutableClock,
) -> AgentCredentialService:
    return AgentCredentialService(
        access=access,
        groups=groups,
        store=store,
        clock=clock,
        generator=SecureAgentCredentialGenerator(),
    )


@pytest.fixture
def create_request(clock: MutableClock) -> CreateAgent:
    return CreateAgent(
        display_name="Build agent",
        group_id="agent-group",
        expires_at=clock.now() + timedelta(days=1),
    )


@pytest_asyncio.fixture
async def issued(
    service: AgentCredentialService,
    administrator: AdministratorPrincipal,
    create_request: CreateAgent,
) -> IssuedAgentCredential:
    return await service.create(administrator, create_request)


@pytest_asyncio.fixture
async def non_expiring(
    service: AgentCredentialService,
    administrator: AdministratorPrincipal,
    create_request: CreateAgent,
) -> IssuedAgentCredential:
    request = CreateAgent(
        display_name=create_request.display_name,
        group_id=create_request.group_id,
        expires_at=NeverExpires.NEVER,
    )
    return await service.create(administrator, request)
