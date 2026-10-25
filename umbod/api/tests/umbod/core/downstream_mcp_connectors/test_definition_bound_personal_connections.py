from tests.umbod.core.downstream_mcp_connectors.personal_caller_support import captured_personal_caller
import asyncio
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio

from tests.persistence_runtime import prepared_inmemory_runtime, prepared_sqlite_runtime
from umbod.core.capabilities.descriptions import SystemConnectorCapabilityDescriptionOverrideStore
from umbod.core.connectors.downstream_mcp.management import (
    DeleteDownstreamConnectorAggregate,
    DownstreamConnectorUnitOfWork,
)
from umbod.core.connectors.downstream_mcp.models import OAuthConnectorDefinition
from umbod.core.connectors.downstream_mcp.personal_connections import (
    Authorized,
    CanonicalPrincipal,
    PersonalConnection,
    PersonalConnectionKey,
    PersonalConnectionService,
    PersonalConnectionState,
    PersonalConnectionStore,
    ReplacePersonalAuthorization,
    SetPersonalConnectionEnabled,
)
from umbod.core.connectors.downstream_mcp.personal_connections.inventory import PersonalConnectorInventoryService
from umbod.core.callers import GroupMembership
from umbod.core.connectors.downstream_mcp.personal_connections.inventory_models import (
    PersonalConnectorUnavailable,
    SetPersonalConnectorEnablement,
)
from umbod.core.connectors.downstream_mcp.stores import (
    DownstreamMcpStores,
    SaveConnectorDefinition,
    create_downstream_mcp_stores,
)
from umbod.core.permissions.domain import GroupPermissionSet, GroupPermissionSummary


@pytest_asyncio.fixture(params=("inmemory", "sqlite"))
async def stores(request: pytest.FixtureRequest, tmp_path: Path) -> AsyncIterator[DownstreamMcpStores]:
    runtime = (
        await prepared_inmemory_runtime()
        if request.param == "inmemory"
        else await prepared_sqlite_runtime(tmp_path / "bound.sqlite3")
    )
    bundle = await create_downstream_mcp_stores("bound-secret", runtime.database)
    await bundle.definitions.save(SaveConnectorDefinition(definition=OAuthConnectorDefinition(
        connector_id="personal",
        display_name="Personal",
        capability_description="Personal connector capabilities",
        endpoint_url="https://personal.example/mcp",
        authorization_mode="personal",
    )))
    yield bundle


@pytest.fixture
def key() -> PersonalConnectionKey:
    return PersonalConnectionKey(
        principal=CanonicalPrincipal(namespace="test:catalogue", subject="owner"),
        connector_id="personal",
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ("enable", "disable", "disconnect", "authorization"))
async def test_factory_store_refuses_all_mutations_after_connector_deletion(
    stores: DownstreamMcpStores, key: PersonalConnectionKey, operation: str
) -> None:
    store: PersonalConnectionStore = stores.personal_connections
    current = await store.set_enabled(SetPersonalConnectionEnabled(key=key, enabled=True))
    assert isinstance(current, PersonalConnection)
    await stores.unit_of_work.delete(DeleteDownstreamConnectorAggregate(connector_id=key.connector_id))
    with pytest.raises(PersonalConnectorUnavailable):
        if operation == "disconnect":
            await store.disconnect(key)
        elif operation == "authorization":
            await store.replace_authorization(ReplacePersonalAuthorization(
                key=key,
                expected_revision=current.revision,
                authorization=Authorized(authorization="stale-refresh"),
            ))
        else:
            await store.set_enabled(SetPersonalConnectionEnabled(key=key, enabled=operation == "enable"))
    assert not isinstance(await store.get(key), PersonalConnection)


@pytest.mark.asyncio
async def test_factory_store_rejects_shared_oauth_target(
    stores: DownstreamMcpStores, key: PersonalConnectionKey
) -> None:
    await stores.definitions.save(SaveConnectorDefinition(definition=OAuthConnectorDefinition(
        connector_id=key.connector_id,
        display_name="Shared",
        capability_description="Shared connector capabilities",
        endpoint_url="https://shared.example/mcp",
        authorization_mode="shared",
    )))
    with pytest.raises(PersonalConnectorUnavailable):
        await stores.personal_connections.set_enabled(SetPersonalConnectionEnabled(key=key, enabled=True))
    assert not isinstance(await stores.personal_connections.get(key), PersonalConnection)


@pytest.mark.asyncio
@pytest.mark.parametrize("delete_first", (True, False))
async def test_competing_mutation_and_aggregate_deletion_leave_no_personal_row(
    stores: DownstreamMcpStores, key: PersonalConnectionKey, delete_first: bool
) -> None:
    mutation = stores.personal_connections.set_enabled(SetPersonalConnectionEnabled(key=key, enabled=True))
    deletion = stores.unit_of_work.delete(DeleteDownstreamConnectorAggregate(connector_id=key.connector_id))
    operations = (deletion, mutation) if delete_first else (mutation, deletion)
    results = await asyncio.gather(*operations, return_exceptions=True)
    assert all(
        result is None or isinstance(result, (PersonalConnection, PersonalConnectorUnavailable))
        for result in results
    )
    assert not isinstance(await stores.personal_connections.get(key), PersonalConnection)


class GrantedGroups:
    async def list_group_identifiers(self) -> tuple[GroupPermissionSummary, ...]:
        return (GroupPermissionSummary(group_id="team"),)

    async def list_group_permissions(self, group_id: str) -> GroupPermissionSet:
        return GroupPermissionSet(group_id=group_id, connector_ids=("personal",), capabilities=())

    async def list_all_group_permissions(self) -> tuple[GroupPermissionSet, ...]:
        return (await self.list_group_permissions("team"),)


class DeleteBeforeMutationStore:
    def __init__(self, store: PersonalConnectionStore, unit_of_work: DownstreamConnectorUnitOfWork) -> None:
        self._store = store
        self._unit_of_work = unit_of_work

    async def get(self, key: PersonalConnectionKey) -> PersonalConnectionState:
        return await self._store.get(key)

    async def set_enabled(self, command: SetPersonalConnectionEnabled) -> PersonalConnectionState:
        await self._unit_of_work.delete(DeleteDownstreamConnectorAggregate(connector_id=command.key.connector_id))
        return await self._store.set_enabled(command)

    async def disconnect(self, key: PersonalConnectionKey) -> PersonalConnectionState:
        return await self._store.disconnect(key)

    async def replace_authorization(self, command: ReplacePersonalAuthorization) -> PersonalConnectionState:
        return await self._store.replace_authorization(command)

    async def delete_connector(self, connector_id: str) -> None:
        await self._store.delete_connector(connector_id)


@pytest.mark.asyncio
async def test_inventory_cannot_recreate_state_when_deleted_after_eligibility_check(
    stores: DownstreamMcpStores, key: PersonalConnectionKey
) -> None:
    await stores.publishing.publish_connector(key.connector_id)
    connections = PersonalConnectionService(
        captured_personal_caller(key.principal, ()),
        DeleteBeforeMutationStore(stores.personal_connections, stores.unit_of_work),
    )
    inventory = PersonalConnectorInventoryService(
        stores.definitions,
        stores.publishing,
        GrantedGroups(),
        GroupMembership(group_ids=("team",)),
        connections,
        SystemConnectorCapabilityDescriptionOverrideStore(),
    )
    with pytest.raises(PersonalConnectorUnavailable):
        await inventory.set_enabled(SetPersonalConnectorEnablement(connector_id=key.connector_id, enabled=True))
    assert not isinstance(await stores.personal_connections.get(key), PersonalConnection)
