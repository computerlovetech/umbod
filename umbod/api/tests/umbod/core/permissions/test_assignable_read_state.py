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
from umbod.core.permissions.read_state import (
    AssignableReadState,
    AssignableStateReads,
    plan_assignable_state,
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
from umbod.core.persistence.plan import ReadPlan, ReadPlanOperations
from umbod.core.publishing.stores.schema import (
    PUBLICATION_STATE_CONNECTOR_ID,
    PUBLICATION_STATE_TABLE,
    PublicationStateRecord,
)


pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture(params=DATABASE_ADAPTERS, ids=lambda adapter: cast(DatabaseAdapter, adapter).name)
async def database(request: pytest.FixtureRequest, tmp_path: Path) -> Database:
    database = cast(DatabaseAdapter, request.param).factory(tmp_path)
    await database.ensure_schema(cast(tuple[Table[BaseModel, BaseModel], ...], (
        PUBLICATION_STATE_TABLE,
        CAPABILITY_ACTIVATION_STATE_TABLE,
    )))
    return database


async def _seed(database: Database) -> None:
    async with database.session(mode=TransactionMode.READ_WRITE) as session:
        for connector_id, published, previously_published in (
            ("personal", True, True),
            ("other", True, True),
            ("historical", False, True),
            ("draft", False, False),
        ):
            await session.insert(PUBLICATION_STATE_TABLE, InsertCommand(row=PublicationStateRecord(
                connector_id=connector_id, published=published,
                previously_published=previously_published, revision=1, updated_at="now",
            )))
        for connector_kind, connector_id, capability_kind, capability_key, status in (
            ("native", "personal", "tool", "same", "enabled"),
            ("native", "other", "tool", "same", "enabled"),
            ("openapi", "other", "prompt", "same", "enabled"),
            ("native", "other", "tool", "disabled", "disabled"),
        ):
            await session.insert(CAPABILITY_ACTIVATION_STATE_TABLE, InsertCommand(
                row=CapabilityActivationStateRecord(
                    connector_kind=connector_kind, connector_id=connector_id,
                    capability_kind=capability_kind, capability_key=capability_key,
                    status=status, updated_at="now",
                )
            ))


async def _load(
    database: Database,
    publication_connector_ids: tuple[str, ...],
    activation_connector_ids: tuple[str, ...],
) -> AssignableReadState:
    plan: ReadPlanOperations = ReadPlan()
    reads: AssignableStateReads = plan_assignable_state(
        plan, publication_connector_ids, activation_connector_ids,
    )
    async with database.session(mode=TransactionMode.READ_WRITE) as session:
        return reads.resolve(await plan.execute(session))


async def test_registration_defers_reads_and_resolved_readers_never_query(database: Database) -> None:
    await _seed(database)
    async with database.session(mode=TransactionMode.READ_WRITE) as session:
        observed = AsyncMock(wraps=session)
        plan: ReadPlanOperations = ReadPlan()
        reads = plan_assignable_state(plan, ("personal", "personal"), ("other", "other"))
        observed.find_many.assert_not_awaited()
        state = reads.resolve(await plan.execute(cast(DatabaseSession, observed)))
        assert observed.find_many.await_count == 2
    for _ in range(3):
        assert await state.publishing.is_published("personal")
        assert await state.publishing.was_previously_published("personal")
        assert await state.activations.get_status(
            CapabilityRef("native", "other", "tool", "same"),
        ) == ActivationStatus.ENABLED
    assert observed.find_many.await_count == 2


async def test_empty_inputs_and_empty_state_exclude_populated_database(database: Database) -> None:
    await _seed(database)
    async with database.session(mode=TransactionMode.READ_WRITE) as session:
        observed = AsyncMock(wraps=session)
        plan = ReadPlan()
        reads = plan_assignable_state(plan, (), ())
        assert reads.publications == ()
        assert reads.activations == ()
        resolved = reads.resolve(await plan.execute(cast(DatabaseSession, observed)))
        observed.find_many.assert_not_awaited()
    for state in (resolved, AssignableReadState.empty()):
        assert not await state.publishing.is_published("personal")
        assert not await state.publishing.was_previously_published("personal")
        assert await state.activations.get_status(
            CapabilityRef("native", "personal", "tool", "same"),
        ) == ActivationStatus.DISABLED


@pytest.mark.parametrize("publication_ids,activation_ids", [(("personal",), ()), ((), ("other",))])
async def test_empty_scope_does_not_suppress_independent_scope(
    database: Database, publication_ids: tuple[str, ...], activation_ids: tuple[str, ...],
) -> None:
    await _seed(database)
    async with database.session(mode=TransactionMode.READ_WRITE) as session:
        observed = AsyncMock(wraps=session)
        plan = ReadPlan()
        reads = plan_assignable_state(plan, publication_ids, activation_ids)
        state = reads.resolve(await plan.execute(cast(DatabaseSession, observed)))
        assert observed.find_many.await_count == 1
    assert await state.publishing.is_published("personal") == bool(publication_ids)
    expected = ActivationStatus.ENABLED if activation_ids else ActivationStatus.DISABLED
    assert await state.activations.get_status(CapabilityRef("native", "other", "tool", "same")) == expected


async def test_scopes_are_independent_and_activation_requires_complete_identity(database: Database) -> None:
    await _seed(database)
    state = await _load(database, ("personal",), ("other",))
    assert await state.publishing.is_published("personal")
    assert not await state.publishing.is_published("other")
    assert not await state.publishing.was_previously_published("other")
    for ref in (
        CapabilityRef("native", "other", "tool", "same"),
        CapabilityRef("openapi", "other", "prompt", "same"),
    ):
        assert await state.activations.get_status(ref) == ActivationStatus.ENABLED
    for ref in (
        CapabilityRef("openapi", "other", "tool", "same"),
        CapabilityRef("native", "other", "prompt", "same"),
        CapabilityRef("native", "personal", "tool", "same"),
        CapabilityRef("native", "missing", "tool", "same"),
        CapabilityRef("native", "other", "tool", "different"),
        CapabilityRef("native", "other", "tool", "disabled"),
    ):
        assert await state.activations.get_status(ref) == ActivationStatus.DISABLED


@pytest.mark.parametrize("connector_id,published,historical", [
    ("personal", True, True),
    ("historical", False, True),
    ("draft", False, False),
    ("missing", False, False),
])
async def test_publication_current_and_historical_flags_are_preserved(
    database: Database, connector_id: str, published: bool, historical: bool,
) -> None:
    await _seed(database)
    state = await _load(database, (connector_id,), ())
    assert await state.publishing.is_published(connector_id) == published
    assert await state.publishing.was_previously_published(connector_id) == historical


async def test_frozen_plan_reexecution_observes_mutation_without_changing_prior_state(database: Database) -> None:
    await _seed(database)
    plan = ReadPlan()
    reads = plan_assignable_state(plan, ("personal",), ("other",))
    async with database.session(mode=TransactionMode.READ_WRITE) as session:
        previous = reads.resolve(await plan.execute(session))
    with pytest.raises(RuntimeError, match="registration is frozen"):
        plan_assignable_state(plan, ("additional",), ())
    async with database.session(mode=TransactionMode.READ_WRITE) as session:
        await session.delete(PUBLICATION_STATE_TABLE, DeleteQuery(Equals(PUBLICATION_STATE_CONNECTOR_ID, "personal")))
        await session.delete(CAPABILITY_ACTIVATION_STATE_TABLE, DeleteQuery(Equals(CAPABILITY_ACTIVATION_STATE_CONNECTOR_ID, "other")))
    async with database.session(mode=TransactionMode.READ_WRITE) as session:
        current = reads.resolve(await plan.execute(session))
    ref = CapabilityRef("native", "other", "tool", "same")
    assert await previous.publishing.is_published("personal")
    assert await previous.publishing.was_previously_published("personal")
    assert await previous.activations.get_status(ref) == ActivationStatus.ENABLED
    assert not await current.publishing.is_published("personal")
    assert not await current.publishing.was_previously_published("personal")
    assert await current.activations.get_status(ref) == ActivationStatus.DISABLED


async def test_large_independent_scopes_are_deduplicated_into_five_batches(database: Database) -> None:
    publication_ids = tuple(str(index) for index in range(401))
    activation_ids = publication_ids[:201]
    async with database.session(mode=TransactionMode.READ_WRITE) as session:
        for identifier in publication_ids:
            await session.insert(PUBLICATION_STATE_TABLE, InsertCommand(row=PublicationStateRecord(
                connector_id=identifier, published=True, previously_published=True,
                revision=1, updated_at="now",
            )))
            await session.insert(CAPABILITY_ACTIVATION_STATE_TABLE, InsertCommand(row=CapabilityActivationStateRecord(
                connector_kind="native", connector_id=identifier, capability_kind="tool",
                capability_key="read", status="enabled", updated_at="now",
            )))
        observed = AsyncMock(wraps=session)
        plan = ReadPlan()
        reads = plan_assignable_state(plan, publication_ids + publication_ids, activation_ids + activation_ids)
        assert len(reads.publications) == 3
        assert len(reads.activations) == 2
        observed.find_many.assert_not_awaited()
        state = reads.resolve(await plan.execute(cast(DatabaseSession, observed)))
        assert observed.find_many.await_count == 5
    for identifier in publication_ids:
        assert await state.publishing.is_published(identifier)
        assert await state.publishing.was_previously_published(identifier)
        expected = ActivationStatus.ENABLED if identifier in activation_ids else ActivationStatus.DISABLED
        assert await state.activations.get_status(CapabilityRef("native", identifier, "tool", "read")) == expected
