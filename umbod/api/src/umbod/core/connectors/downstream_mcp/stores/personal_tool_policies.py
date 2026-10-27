from collections.abc import Callable

from messaging.events import McpGroupPermissionChanged
from umbod.core.activation.events import connector_capability_activation_changed_event
from umbod.core.configuration.events import connector_configuration_changed_event
from umbod.core.messaging.stores.event_stream import append_event_in_session
from datetime import datetime
from uuid import uuid4

from umbod.core.capabilities.tools.names import PublicToolIdentity, PublicToolNameValidator
from umbod.core.persistence import Database, DatabaseSession, DeleteQuery, Equals, NoFilter, TransactionMode, UpsertCommand

from ..models import ToolCatalogSnapshot, uses_personal_oauth
from ..personal_tools import (
    PersonalToolPolicy,
    PersonalToolPolicyConflict,
    PersonalToolPolicyInvalid,
    PersonalToolPolicyReplacement,
    PersonalToolPolicyUnavailable,
    ReplacePersonalToolPolicy,
    UnconfiguredPersonalToolPolicy,
    contract_fingerprint,
)
from .catalogs import find_catalog_record, replace_catalog
from .queries import query_all as _query
from .personal_tools_schema import (
    PERSONAL_TOOL_OBSERVATION_CONNECTOR_ID,
    PERSONAL_TOOL_OBSERVATION_TABLE,
    PERSONAL_TOOL_POLICY_CONNECTOR_ID,
    PERSONAL_TOOL_POLICY_TABLE,
    PersonalToolPolicyKey,
    PersonalToolPolicyRecord,
)
from .ports import CONNECTOR_DEFINITION_ADAPTER, ConnectorIdQuery, ReplaceToolCatalog
from .schema import CONNECTOR_DEFINITION_CONNECTOR_ID, CONNECTOR_DEFINITION_TABLE, TOOL_CATALOG_TABLE


async def load_personal_tool_policy(session: DatabaseSession, connector_id: str) -> PersonalToolPolicy | UnconfiguredPersonalToolPolicy:
    row = await session.find_one(PERSONAL_TOOL_POLICY_TABLE, _query(Equals(PERSONAL_TOOL_POLICY_CONNECTOR_ID, connector_id)))
    if row is None:
        return UnconfiguredPersonalToolPolicy(connector_id=connector_id, tools=())
    policy = PersonalToolPolicy.model_validate_json(row.document)
    if policy.connector_id != connector_id:
        raise PersonalToolPolicyUnavailable("Personal tool policy unavailable")
    return policy


class PersonalToolPolicyStoreService:
    def __init__(self, database: Database, clock: Callable[[], datetime], fault: Callable[[str], None]) -> None:
        self._database = database
        self._clock = clock
        self._fault = fault

    async def get(self, query: ConnectorIdQuery) -> PersonalToolPolicy | UnconfiguredPersonalToolPolicy:
        async with self._database.session(mode=TransactionMode.READ_WRITE) as session:
            row = await session.find_one(CONNECTOR_DEFINITION_TABLE, _query(Equals(CONNECTOR_DEFINITION_CONNECTOR_ID, query.connector_id)))
            if row is None or not uses_personal_oauth(CONNECTOR_DEFINITION_ADAPTER.validate_python(row.document)):
                raise PersonalToolPolicyUnavailable("Personal connector unavailable")
            return await load_personal_tool_policy(session, query.connector_id)

    async def replace(self, command: ReplacePersonalToolPolicy) -> PersonalToolPolicyReplacement:
        async with self._database.session(mode=TransactionMode.SERIALIZED_WRITE) as session:
            replacement, changed = await self._replace(session, command)
            if changed:
                await self._append_events(session, replacement)
            return replacement

    async def _replace(self, session: DatabaseSession, command: ReplacePersonalToolPolicy) -> tuple[PersonalToolPolicyReplacement, bool]:
        row = await session.find_one(CONNECTOR_DEFINITION_TABLE, _query(Equals(CONNECTOR_DEFINITION_CONNECTOR_ID, command.connector_id)))
        if row is None:
            raise PersonalToolPolicyUnavailable("Personal connector unavailable")
        definition = CONNECTOR_DEFINITION_ADAPTER.validate_python(row.document)
        if not uses_personal_oauth(definition):
            raise PersonalToolPolicyUnavailable("Personal connector unavailable")
        previous = await load_personal_tool_policy(session, command.connector_id)
        if previous.revision != command.expected_revision:
            raise PersonalToolPolicyConflict("Personal tool policy revision conflict")
        unchanged = isinstance(previous, PersonalToolPolicy) and previous.tools == command.tools
        if unchanged:
            catalog = await find_catalog_record(session, TOOL_CATALOG_TABLE, command.connector_id)
            expected = ToolCatalogSnapshot(connector_id=previous.connector_id, discovered_at=previous.approved_at, tools=previous.tools)
            if catalog is not None and ToolCatalogSnapshot.model_validate(catalog.snapshot) == expected:
                return PersonalToolPolicyReplacement(policy=previous, changed_tools=(), revoked_grants=()), False
        identities = list(command.native_identities)
        identities.extend(PublicToolIdentity(connector_id=command.connector_id, tool_name_prefix=definition.tool_name_prefix, operation_name=tool.identity.downstream_name) for tool in command.tools)
        for other in await session.find_many(CONNECTOR_DEFINITION_TABLE, _query(NoFilter())):
            if other.connector_id == command.connector_id:
                continue
            catalog = await find_catalog_record(session, TOOL_CATALOG_TABLE, other.connector_id)
            if catalog is not None:
                other_definition = CONNECTOR_DEFINITION_ADAPTER.validate_python(other.document)
                snapshot = ToolCatalogSnapshot.model_validate(catalog.snapshot)
                identities.extend(PublicToolIdentity(connector_id=other.connector_id, tool_name_prefix=other_definition.tool_name_prefix, operation_name=tool.identity.downstream_name) for tool in snapshot.tools)
        try:
            PublicToolNameValidator().validate_unique(tuple(identities))
        except ValueError as error:
            raise PersonalToolPolicyInvalid(str(error)) from error
        if unchanged:
            await self._project(session, previous)
            return PersonalToolPolicyReplacement(policy=previous, changed_tools=(), revoked_grants=()), True
        policy = PersonalToolPolicy(connector_id=command.connector_id, revision=str(uuid4()), approved_at=self._clock(), tools=command.tools)
        old = {tool.identity.downstream_name: contract_fingerprint(tool) for tool in previous.tools}
        current = {tool.identity.downstream_name: contract_fingerprint(tool) for tool in policy.tools}
        changed = tuple(sorted(name for name in old.keys() | current.keys() if old.get(name) != current.get(name)))
        self._fault("personal_tool_permissions")
        await session.upsert(PERSONAL_TOOL_POLICY_TABLE, UpsertCommand(key=PersonalToolPolicyKey(connector_id=command.connector_id), row=PersonalToolPolicyRecord(connector_id=command.connector_id, document=policy.model_dump_json())))
        await self._project(session, policy)
        self._fault("personal_tool_policy_saved")
        return PersonalToolPolicyReplacement(policy=policy, changed_tools=changed, revoked_grants=()), True

    async def _append_events(self, session: DatabaseSession, replacement: PersonalToolPolicyReplacement) -> None:
        connector_id = replacement.policy.connector_id
        await append_event_in_session(session, connector_configuration_changed_event(connector_id))
        for name in replacement.changed_tools:
            await append_event_in_session(session, connector_capability_activation_changed_event(
                "downstream_mcp", connector_id, "tool", name,
            ))
        for grant in replacement.revoked_grants:
            await append_event_in_session(session, McpGroupPermissionChanged(
                group_id=grant.group_id, action="revoke", target_kind="tool",
                connector_id=connector_id, capability_kind="tool",
                capability_key=grant.capability_key, operation_name=grant.capability_key,
            ).to_messaging_event())

    async def _project(self, session: DatabaseSession, policy: PersonalToolPolicy) -> None:
        await replace_catalog(session, TOOL_CATALOG_TABLE, ReplaceToolCatalog(snapshot=ToolCatalogSnapshot(connector_id=policy.connector_id, discovered_at=policy.approved_at, tools=policy.tools)))

    async def delete_connector(self, connector_id: str) -> None:
        async with self._database.session(mode=TransactionMode.SERIALIZED_WRITE) as session:
            await session.delete(PERSONAL_TOOL_POLICY_TABLE, DeleteQuery(Equals(PERSONAL_TOOL_POLICY_CONNECTOR_ID, connector_id)))
            await session.delete(PERSONAL_TOOL_OBSERVATION_TABLE, DeleteQuery(Equals(PERSONAL_TOOL_OBSERVATION_CONNECTOR_ID, connector_id)))
