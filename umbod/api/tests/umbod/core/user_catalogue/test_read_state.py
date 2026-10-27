from pathlib import Path
from typing import cast
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from pydantic import BaseModel

from tests.umbod.core.persistence.contract_support import DATABASE_ADAPTERS, DatabaseAdapter
from umbod.core.activation.domain import ActivationStatus, CapabilityRef
from umbod.core.activation.stores.schema import (
    CAPABILITY_ACTIVATION_STATE_CONNECTOR_ID,
    CAPABILITY_ACTIVATION_STATE_TABLE,
    CapabilityActivationStateRecord,
)
from umbod.core.permissions.domain import ConnectorCapabilityRef, GroupPermissionSet
from umbod.core.permissions.stores.schema import (
    CAPABILITY_PERMISSION_GROUP_ID,
    CAPABILITY_PERMISSION_TABLE,
    CONNECTOR_PERMISSION_TABLE,
    GroupCapabilityPermissionRecord,
    GroupConnectorPermissionRecord,
)
from umbod.core.persistence import (
    Database,
    DatabaseSession,
    DeleteQuery,
    Equals,
    InsertCommand,
    Table,
    TransactionMode,
)
from umbod.core.persistence.plan import ReadPlan
from umbod.core.publishing.stores.schema import (
    PUBLICATION_STATE_CONNECTOR_ID,
    PUBLICATION_STATE_TABLE,
    PublicationStateRecord,
)
from umbod.core.user_catalogue.read_state import CatalogueReadState, plan_catalogue_state


pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture(params=DATABASE_ADAPTERS, ids=lambda adapter: cast(DatabaseAdapter, adapter).name)
async def database(request: pytest.FixtureRequest, tmp_path: Path) -> Database:
    database = cast(DatabaseAdapter, request.param).factory(tmp_path)
    await database.ensure_schema(cast(tuple[Table[BaseModel, BaseModel], ...], (
        PUBLICATION_STATE_TABLE,
        CAPABILITY_ACTIVATION_STATE_TABLE,
        CONNECTOR_PERMISSION_TABLE,
        CAPABILITY_PERMISSION_TABLE,
    )))
    return database


async def _load(
    database: Database, connector_ids: tuple[str, ...], group_ids: tuple[str, ...]
) -> CatalogueReadState:
    plan = ReadPlan()
    reads = plan_catalogue_state(plan, connector_ids, group_ids)
    async with database.session(mode=TransactionMode.READ_WRITE) as session:
        return reads.resolve(await plan.execute(session))


async def _seed(database: Database) -> None:
    async with database.session(mode=TransactionMode.READ_WRITE) as session:
        await session.insert(PUBLICATION_STATE_TABLE, InsertCommand(row=PublicationStateRecord(
            connector_id="a", published=True, previously_published=True,
            revision=1, updated_at="now",
        )))
        await session.insert(PUBLICATION_STATE_TABLE, InsertCommand(row=PublicationStateRecord(
            connector_id="b", published=True, previously_published=True,
            revision=1, updated_at="now",
        )))
        for connector_kind, capability_kind in (("native", "tool"), ("openapi", "prompt")):
            await session.insert(CAPABILITY_ACTIVATION_STATE_TABLE, InsertCommand(
                row=CapabilityActivationStateRecord(
                    connector_kind=connector_kind, connector_id="a",
                    capability_kind=capability_kind, capability_key="same",
                    status="enabled", updated_at="now",
                )
            ))
        for group_id in ("caller", "other"):
            for connector_id in ("z", "a"):
                await session.insert(CONNECTOR_PERMISSION_TABLE, InsertCommand(
                    row=GroupConnectorPermissionRecord(group_id=group_id, connector_id=connector_id)
                ))
                for capability_kind in ("tool", "prompt"):
                    await session.insert(CAPABILITY_PERMISSION_TABLE, InsertCommand(
                        row=GroupCapabilityPermissionRecord(
                            group_id=group_id, connector_id=connector_id,
                            capability_kind=capability_kind, capability_key="same",
                        )
                    ))


async def test_registration_defers_four_bulk_reads_and_readers_never_query(database: Database) -> None:
    await _seed(database)
    async with database.session(mode=TransactionMode.READ_WRITE) as session:
        observed = AsyncMock(wraps=session)
        plan = ReadPlan()
        reads = plan_catalogue_state(
            plan, tuple(str(index) for index in range(100)) + ("a", "a"),
            tuple(str(index) for index in range(100)) + ("caller", "caller"),
        )
        observed.find_many.assert_not_awaited()
        state = reads.resolve(await plan.execute(cast(DatabaseSession, observed)))
        assert observed.find_many.await_count == 4
    for _ in range(3):
        assert await state.publishing.is_published("a")
        assert await state.publishing.was_previously_published("a")
        assert await state.activations.get_status(CapabilityRef("native", "a", "tool", "same")) == ActivationStatus.ENABLED
        assert (await state.permissions.list_group_permissions("caller")).connector_ids == ("a", "z")
    assert observed.find_many.await_count == 4


async def test_empty_inputs_register_no_reads_and_missing_facts_fail_closed(database: Database) -> None:
    await _seed(database)
    async with database.session(mode=TransactionMode.READ_WRITE) as session:
        observed = AsyncMock(wraps=session)
        plan = ReadPlan()
        reads = plan_catalogue_state(plan, (), ())
        state = reads.resolve(await plan.execute(cast(DatabaseSession, observed)))
        observed.find_many.assert_not_awaited()
    assert not await state.publishing.is_published("a")
    assert not await state.publishing.was_previously_published("a")
    assert await state.activations.get_status(CapabilityRef("native", "a", "tool", "same")) == ActivationStatus.DISABLED
    assert await state.permissions.list_group_permissions("caller") == GroupPermissionSet("caller", (), ())


async def test_reads_are_scoped_and_activation_uses_complete_compound_identity(database: Database) -> None:
    await _seed(database)
    state = await _load(database, ("a",), ("caller",))
    for ref in (
        CapabilityRef("openapi", "a", "tool", "same"),
        CapabilityRef("native", "a", "prompt", "same"),
        CapabilityRef("native", "b", "tool", "same"),
        CapabilityRef("native", "a", "tool", "different"),
    ):
        assert await state.activations.get_status(ref) == ActivationStatus.DISABLED
    assert await state.activations.get_status(CapabilityRef("openapi", "a", "prompt", "same")) == ActivationStatus.ENABLED
    assert not await state.publishing.is_published("b")
    assert await state.permissions.list_group_permissions("other") == GroupPermissionSet("other", (), ())
    assert (await state.permissions.list_group_permissions("caller")).capabilities == (
        ConnectorCapabilityRef("a", "prompt", "same"),
        ConnectorCapabilityRef("a", "tool", "same"),
        ConnectorCapabilityRef("z", "prompt", "same"),
        ConnectorCapabilityRef("z", "tool", "same"),
    )


async def test_fresh_requests_observe_revocations_without_mutating_prior_snapshot(database: Database) -> None:
    await _seed(database)
    previous = await _load(database, ("a",), ("caller",))
    async with database.session(mode=TransactionMode.READ_WRITE) as session:
        await session.delete(PUBLICATION_STATE_TABLE, DeleteQuery(Equals(PUBLICATION_STATE_CONNECTOR_ID, "a")))
        await session.delete(CAPABILITY_PERMISSION_TABLE, DeleteQuery(Equals(CAPABILITY_PERMISSION_GROUP_ID, "caller")))
        await session.delete(CAPABILITY_ACTIVATION_STATE_TABLE, DeleteQuery(Equals(CAPABILITY_ACTIVATION_STATE_CONNECTOR_ID, "a")))
    current = await _load(database, ("a",), ("caller",))
    assert await previous.publishing.is_published("a")
    assert (await previous.permissions.list_group_permissions("caller")).capabilities
    ref = CapabilityRef("native", "a", "tool", "same")
    assert await previous.activations.get_status(ref) == ActivationStatus.ENABLED
    assert await current.activations.get_status(ref) == ActivationStatus.DISABLED
    assert not await current.publishing.is_published("a")
    assert not (await current.permissions.list_group_permissions("caller")).capabilities
    assert (await current.permissions.list_group_permissions("caller")).connector_ids == ("a", "z")


async def _seed_identifiers(session: DatabaseSession, identifiers: tuple[str, ...]) -> None:
    for identifier in identifiers:
        await session.insert(PUBLICATION_STATE_TABLE, InsertCommand(row=PublicationStateRecord(
            connector_id=identifier, published=True, previously_published=True,
            revision=1, updated_at="now",
        )))
        await session.insert(CAPABILITY_ACTIVATION_STATE_TABLE, InsertCommand(row=CapabilityActivationStateRecord(
            connector_kind="native", connector_id=identifier, capability_kind="tool",
            capability_key="read", status="enabled", updated_at="now",
        )))
        await session.insert(CONNECTOR_PERMISSION_TABLE, InsertCommand(row=GroupConnectorPermissionRecord(
            group_id=identifier, connector_id=identifier,
        )))
        await session.insert(CAPABILITY_PERMISSION_TABLE, InsertCommand(row=GroupCapabilityPermissionRecord(
            group_id=identifier, connector_id=identifier, capability_kind="tool", capability_key="read",
        )))


async def test_large_inputs_are_deduplicated_and_split_into_bounded_batches(database: Database) -> None:
    identifiers = tuple(str(index) for index in range(401))
    async with database.session(mode=TransactionMode.READ_WRITE) as session:
        await _seed_identifiers(session, identifiers)
        observed = AsyncMock(wraps=session)
        plan = ReadPlan()
        reads = plan_catalogue_state(plan, identifiers + identifiers, identifiers + identifiers)
        state = reads.resolve(await plan.execute(cast(DatabaseSession, observed)))
        assert observed.find_many.await_count == 12
    for identifier in identifiers:
        assert await state.publishing.is_published(identifier)
        assert await state.activations.get_status(CapabilityRef("native", identifier, "tool", "read")) == ActivationStatus.ENABLED
        assert await state.permissions.list_group_permissions(identifier) == GroupPermissionSet(
            identifier, (identifier,), (ConnectorCapabilityRef(identifier, "tool", "read"),),
        )
