import asyncio
import json
from dataclasses import FrozenInstanceError

import pytest
from pydantic import ValidationError

from tests.umbod.core.downstream_mcp_connectors.test_personal_runtime_authorizations import RuntimeCase, runtime_case
from tests.umbod.core.downstream_mcp_connectors.test_personal_tools_s3_contracts import InventoryTransport, approved_tool, replace_policy
from umbod.core.configuration.persistence import AuthenticatedTextCipher
from umbod.core.connectors.downstream_mcp.models import DiscoveredTool, DiscoveredToolWithOutputSchema, ToolIdentity
from umbod.core.connectors.downstream_mcp.personal_connections import CanonicalPrincipal, PersonalConnectionKey
from umbod.core.connectors.downstream_mcp.personal_connections.runtime_models import PersonalRuntimeTarget, PersonalRuntimeUnavailable, PersonalToolInventory
from umbod.core.connectors.downstream_mcp.personal_tools import MissingInventoryRevision, PersonalToolDiscoveryService, PersonalToolObservation, PresentInventoryRevision, SavePersonalToolObservation
from umbod.core.connectors.downstream_mcp.stores import ConnectorIdQuery
from umbod.core.connectors.downstream_mcp.stores.personal_tools_schema import PERSONAL_TOOL_OBSERVATION_TABLE, PersonalToolObservationRecord, PersonalToolObservationRecordKey
from umbod.core.persistence import AllFields, NoFilter, Query, TransactionMode, Unordered, UpsertCommand

__all__ = ["runtime_case"]


def discovery(case: RuntimeCase, tools: tuple[DiscoveredTool, ...]) -> PersonalToolDiscoveryService:
    return PersonalToolDiscoveryService(case.store, case.bundle.personal_tool_access, InventoryTransport(tools), lambda: case.query.now)


async def observation_row(case: RuntimeCase) -> PersonalToolObservationRecord:
    async with case.database.session(mode=TransactionMode.READ_WRITE) as session:
        rows = await session.find_many(PERSONAL_TOOL_OBSERVATION_TABLE, Query(filter=NoFilter(), projection=AllFields(), ordering=Unordered()))
    return rows[0]


async def replace_document(case: RuntimeCase, document: str) -> None:
    key = PersonalToolObservationRecordKey(namespace=case.query.key.principal.namespace, subject=case.query.key.principal.subject, connector_id=case.query.key.connector_id)
    async with case.database.session(mode=TransactionMode.SERIALIZED_WRITE) as session:
        await session.upsert(PERSONAL_TOOL_OBSERVATION_TABLE, UpsertCommand(key=key, row=PersonalToolObservationRecord(**key.model_dump(), document=document)))


@pytest.mark.asyncio
async def test_new_tools_require_explicit_rediscovery_without_admin_tool_policy(runtime_case: RuntimeCase) -> None:
    access = runtime_case.bundle.personal_tool_access
    assert await access.read_inventory_revision(runtime_case.query) == MissingInventoryRevision(kind="missing")
    assert await access.list_available(runtime_case.query) == ()
    first = approved_tool("read")
    await discovery(runtime_case, (first,)).discover(runtime_case.query)
    before = await access.list_available(runtime_case.query)
    assert tuple(record.tool for record in before) == (first,)
    result = await discovery(runtime_case, (first, approved_tool("future"))).discover(runtime_case.query)
    after = await access.list_available(runtime_case.query)
    assert result.tool_count == 2
    assert tuple(record.tool.identity.downstream_name for record in after) == ("read", "future")
    assert after[0].inventory_revision != before[0].inventory_revision
    assert not (await runtime_case.bundle.catalogs.get(ConnectorIdQuery(connector_id="personal"))).found


@pytest.mark.asyncio
async def test_admin_policy_replacement_cannot_invalidate_private_inventory(runtime_case: RuntimeCase) -> None:
    await discovery(runtime_case, (approved_tool("read"),)).discover(runtime_case.query)
    access = runtime_case.bundle.personal_tool_access
    before = await access.list_available(runtime_case.query)
    await replace_policy(runtime_case, (approved_tool("unrelated"),))
    await replace_policy(runtime_case, ())
    assert await access.list_available(runtime_case.query) == before


class BlockingInventory:
    def __init__(self, tools: tuple[DiscoveredTool, ...]) -> None:
        self.tools = tools
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    async def list_tools(self, target: PersonalRuntimeTarget) -> PersonalToolInventory:
        self.started.set()
        await self.release.wait()
        return PersonalToolInventory(tools=self.tools)


@pytest.mark.asyncio
@pytest.mark.parametrize("existing", (False, True))
async def test_overlapping_discoveries_cannot_overwrite_completed_inventory(runtime_case: RuntimeCase, existing: bool) -> None:
    if existing:
        await discovery(runtime_case, (approved_tool("initial"),)).discover(runtime_case.query)
    blocked = BlockingInventory((approved_tool("older"),))
    service = PersonalToolDiscoveryService(runtime_case.store, runtime_case.bundle.personal_tool_access, blocked, lambda: runtime_case.query.now)
    pending = asyncio.create_task(service.discover(runtime_case.query))
    await blocked.started.wait()
    await discovery(runtime_case, (approved_tool("newer"),)).discover(runtime_case.query)
    winner = await runtime_case.bundle.personal_tool_access.list_available(runtime_case.query)
    blocked.release.set()
    with pytest.raises(PersonalRuntimeUnavailable):
        await pending
    assert await runtime_case.bundle.personal_tool_access.list_available(runtime_case.query) == winner
    assert winner[0].tool.identity.downstream_name == "newer"


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ("cancelled", "invalid_schema"))
async def test_failed_discovery_preserves_previous_inventory(runtime_case: RuntimeCase, failure: str) -> None:
    await discovery(runtime_case, (approved_tool("initial"),)).discover(runtime_case.query)
    before = await runtime_case.bundle.personal_tool_access.list_available(runtime_case.query)
    blocked = BlockingInventory((approved_tool("replacement"),))
    service = PersonalToolDiscoveryService(runtime_case.store, runtime_case.bundle.personal_tool_access, blocked, lambda: runtime_case.query.now)
    pending = asyncio.create_task(service.discover(runtime_case.query))
    await blocked.started.wait()
    if failure == "cancelled":
        pending.cancel()
        with pytest.raises(asyncio.CancelledError):
            await pending
    else:
        blocked.tools = (approved_tool("invalid").model_copy(update={"input_schema": {"$ref": "https://example.org/schema"}}),)
        blocked.release.set()
        with pytest.raises(PersonalRuntimeUnavailable):
            await pending
    assert await runtime_case.bundle.personal_tool_access.list_available(runtime_case.query) == before


@pytest.mark.asyncio
@pytest.mark.parametrize("invalidity", ("duplicate", "foreign", "oversized", "nonfinite", "output_reference"))
async def test_invalid_inventory_cannot_replace_valid_cache(runtime_case: RuntimeCase, invalidity: str) -> None:
    await discovery(runtime_case, (approved_tool("initial"),)).discover(runtime_case.query)
    before = await observation_row(runtime_case)
    tool = approved_tool("replacement")
    tools = (tool,)
    if invalidity == "duplicate":
        tools = (tool, tool)
    elif invalidity == "foreign":
        tools = (tool.model_copy(update={"identity": ToolIdentity(connector_id="foreign", downstream_name="replacement")}),)
    elif invalidity == "oversized":
        tools = (tool.model_copy(update={"description": "x" * 131072}),)
    elif invalidity == "nonfinite":
        tools = (tool.model_copy(update={"meta": {"value": float("nan")}}),)
    else:
        tools = (DiscoveredToolWithOutputSchema(**tool.model_dump(exclude={"output_schema_status"}), output_schema={"$ref": "https://example.org/schema"}),)
    with pytest.raises(PersonalRuntimeUnavailable):
        await discovery(runtime_case, tools).discover(runtime_case.query)
    assert await observation_row(runtime_case) == before


@pytest.mark.asyncio
async def test_inventory_count_is_bounded_at_private_save_boundary(runtime_case: RuntimeCase) -> None:
    target = await runtime_case.store.resolve(runtime_case.query)
    with pytest.raises(ValidationError):
        SavePersonalToolObservation(query=runtime_case.query, target=target, expected_inventory_revision=MissingInventoryRevision(kind="missing"), tools=tuple(approved_tool(str(index)) for index in range(257)), expires_at=target.expires_at)


@pytest.mark.asyncio
async def test_legacy_match_cache_requires_explicit_discovery_without_reconstruction(runtime_case: RuntimeCase) -> None:
    await discovery(runtime_case, (approved_tool("read"),)).discover(runtime_case.query)
    cipher = AuthenticatedTextCipher("runtime-secret")
    row = await observation_row(runtime_case)
    observation = PersonalToolObservation.model_validate_json(cipher.decrypt(row.document))
    legacy = observation.model_dump(mode="json", exclude={"version", "inventory_revision", "tools"})
    legacy.update({"contract_revision": "legacy", "matches": [{"name": "read", "fingerprint": "0" * 64}]})
    await replace_document(runtime_case, cipher.encrypt(json.dumps(legacy)))
    access = runtime_case.bundle.personal_tool_access
    assert await access.list_available(runtime_case.query) == ()
    assert await access.read_inventory_revision(runtime_case.query) == MissingInventoryRevision(kind="missing")
    await discovery(runtime_case, (approved_tool("new"),)).discover(runtime_case.query)
    assert (await access.list_available(runtime_case.query))[0].tool.identity.downstream_name == "new"


@pytest.mark.asyncio
@pytest.mark.parametrize("invalidity", ("ciphertext", "malformed", "foreign_owner"))
async def test_invalid_encrypted_inventory_fails_closed(runtime_case: RuntimeCase, invalidity: str) -> None:
    await discovery(runtime_case, (approved_tool("private"),)).discover(runtime_case.query)
    cipher = AuthenticatedTextCipher("runtime-secret")
    row = await observation_row(runtime_case)
    assert "private" not in row.document
    observation = PersonalToolObservation.model_validate_json(cipher.decrypt(row.document))
    if invalidity == "foreign_owner":
        key = PersonalConnectionKey(principal=CanonicalPrincipal(namespace="trusted", subject="foreign"), connector_id="personal")
        document = cipher.encrypt(observation.model_copy(update={"key": key}).model_dump_json())
    elif invalidity == "malformed":
        document = cipher.encrypt('{"version":2}')
    else:
        document = "tampered"
    await replace_document(runtime_case, document)
    assert await runtime_case.bundle.personal_tool_access.list_available(runtime_case.query) == ()
    with pytest.raises(PersonalRuntimeUnavailable):
        await runtime_case.bundle.personal_tool_access.read_inventory_revision(runtime_case.query)


@pytest.mark.asyncio
async def test_private_inventory_dtos_are_frozen_and_revision_is_owner_specific(runtime_case: RuntimeCase) -> None:
    await discovery(runtime_case, (approved_tool("read"),)).discover(runtime_case.query)
    revision = await runtime_case.bundle.personal_tool_access.read_inventory_revision(runtime_case.query)
    assert isinstance(revision, PresentInventoryRevision)
    with pytest.raises((ValidationError, FrozenInstanceError)):
        revision.revision = "replacement"
