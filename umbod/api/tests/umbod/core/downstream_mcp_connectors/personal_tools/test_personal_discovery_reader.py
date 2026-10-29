from datetime import timedelta
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from tests.umbod.core.downstream_mcp_connectors.personal_discovery_audit import DiscoveryReadAudit, RowT, KeyT, ResultT
from umbod.core.persistence import ReadSession, Table
from umbod.core.connectors.downstream_mcp.personal_connections import SetPersonalConnectionEnabled

import pytest
from pydantic import ValidationError

from tests.umbod.core.downstream_mcp_connectors.personal_discovery_audit import AuditedDatabase, RestrictedCipher
from tests.umbod.core.downstream_mcp_connectors.personal_discovery_support import read_available
from tests.umbod.core.downstream_mcp_connectors.test_personal_runtime_authorizations import RuntimeCase, runtime_case
from tests.umbod.core.downstream_mcp_connectors.test_personal_tools_s3_contracts import approved_tool, replace_policy, save_matches
from umbod.core.configuration.persistence import AuthenticatedTextCipher
from umbod.core.connectors.downstream_mcp.personal_connections.models import CanonicalPrincipal, PersonalConnectionKey
from umbod.core.connectors.downstream_mcp.personal_tools import PersonalToolDiscoveryQuery
from umbod.core.connectors.downstream_mcp.stores.personal_discovery_schema import PERSONAL_DISCOVERY_TABLE
from umbod.core.connectors.downstream_mcp.stores.personal_tool_discovery import PersonalToolDiscoveryStore
from umbod.core.connectors.downstream_mcp.stores.personal_tools_schema import PERSONAL_TOOL_OBSERVATION_TABLE
from umbod.core.connectors.downstream_mcp.stores.schema import PersonalConnectionRecordKey
from umbod.core.persistence import AllFields, NoFilter, Query, TransactionMode, Unordered, UpsertCommand

__all__ = ["runtime_case"]


async def discovery_query(case: RuntimeCase) -> PersonalToolDiscoveryQuery:
    return PersonalToolDiscoveryQuery(principal=case.query.key.principal, definitions=(await case.bundle.definitions.list()).definitions, now=case.query.now)


@pytest.mark.asyncio
async def test_discovery_reads_one_snapshot_and_never_reads_or_decrypts_credentials(runtime_case: RuntimeCase) -> None:
    policy = await replace_policy(runtime_case, (approved_tool("first"), approved_tool("second")))
    await save_matches(runtime_case, policy)
    permitted: set[str] = set()
    async with runtime_case.database.read_session() as session:
        for table in (PERSONAL_DISCOVERY_TABLE, PERSONAL_TOOL_OBSERVATION_TABLE):
            rows = await session.find_many(table, Query(filter=NoFilter(), projection=AllFields(), ordering=Unordered()))
            permitted.update(row.document for row in rows)
    database = AuditedDatabase(runtime_case.database, discovery_only=True)
    cipher = RestrictedCipher(AuthenticatedTextCipher("runtime-secret"), frozenset(permitted))
    reader = PersonalToolDiscoveryStore(database, cipher)
    query = await discovery_query(runtime_case)
    selected = query.definitions + (query.definitions[0].model_copy(update={"connector_id": "another"}),)
    records = await reader.read(query.model_copy(update={"definitions": selected}))
    assert tuple(record.tool.identity.downstream_name for record in records) == ("first", "second")
    assert database.read_sessions == 1
    assert database.write_sessions == 0
    assert database.audits[0].reads == 3
    assert cipher.decryptions == 2
    with pytest.raises(ValidationError):
        records[0].inventory_revision = "changed"


@pytest.mark.asyncio
@pytest.mark.parametrize("change,visible", [("display_name", True), ("tool_name_prefix", True), ("endpoint_url", False), ("foreign_owner", False), ("expired", False), ("future", False)])
async def test_discovery_checks_security_binding_not_display_metadata(runtime_case: RuntimeCase, change: str, visible: bool) -> None:
    await save_matches(runtime_case, await replace_policy(runtime_case, (approved_tool("read"),)))
    query = await discovery_query(runtime_case)
    definition = query.definitions[0]
    if change in ("display_name", "tool_name_prefix", "endpoint_url"):
        definition = definition.model_copy(update={change: "https://different.example/mcp" if change == "endpoint_url" else "Renamed"})
        query = query.model_copy(update={"definitions": (definition,)})
    elif change == "foreign_owner":
        query = query.model_copy(update={"principal": CanonicalPrincipal(namespace="trusted", subject="foreign")})
    else:
        query = query.model_copy(update={"now": query.now + (timedelta(hours=2) if change == "expired" else -timedelta(hours=2))})
    records = await runtime_case.bundle.personal_tool_discovery.read(query)
    assert bool(records) is visible
    if visible:
        assert records[0].definition == definition


@pytest.mark.asyncio
@pytest.mark.parametrize("invalidity", ["missing", "corrupt", "foreign_owner"])
async def test_missing_or_corrupt_availability_fails_closed(runtime_case: RuntimeCase, invalidity: str) -> None:
    from umbod.core.persistence import DeleteQuery

    await save_matches(runtime_case, await replace_policy(runtime_case, (approved_tool("read"),)))
    async with runtime_case.database.session(mode=TransactionMode.SERIALIZED_WRITE) as session:
        rows = await session.find_many(PERSONAL_DISCOVERY_TABLE, Query(filter=NoFilter(), projection=AllFields(), ordering=Unordered()))
        row = rows[0]
        if invalidity == "missing":
            await session.delete(PERSONAL_DISCOVERY_TABLE, DeleteQuery(NoFilter()))
        else:
            cipher = AuthenticatedTextCipher("runtime-secret")
            document = row.document
            if invalidity == "foreign_owner":
                import json

                value = json.loads(cipher.decrypt(document))
                value["key"] = PersonalConnectionKey(principal=CanonicalPrincipal(namespace="trusted", subject="foreign"), connector_id="personal").model_dump()
                document = cipher.encrypt(json.dumps(value))
            else:
                document = "corrupt"
            key = PersonalConnectionRecordKey(namespace=row.namespace, subject=row.subject, connector_id=row.connector_id)
            await session.upsert(PERSONAL_DISCOVERY_TABLE, UpsertCommand(key=key, row=row.model_copy(update={"document": document})))
    assert await read_available(runtime_case.bundle, runtime_case.query) == ()


class InterleavedReadAudit(DiscoveryReadAudit):
    def __init__(self, delegate: ReadSession, mutate: Callable[[], Awaitable[None]]) -> None:
        super().__init__(delegate)
        self._mutate = mutate
        self.mutated = False

    async def find_one(self, table: Table[RowT, KeyT], query: Query[RowT, ResultT]) -> ResultT | None:
        result = await super().find_one(table, query)
        if table == PERSONAL_TOOL_OBSERVATION_TABLE and not self.mutated:
            self.mutated = True
            await self._mutate()
        return result


class InterleavedDatabase(AuditedDatabase):
    def __init__(self, case: RuntimeCase, mutate: Callable[[], Awaitable[None]]) -> None:
        super().__init__(case.database, discovery_only=True)
        self._mutate = mutate

    @asynccontextmanager
    async def read_session(self) -> AsyncIterator[ReadSession]:
        self.read_sessions += 1
        async with self._delegate.read_session() as session:
            audit = InterleavedReadAudit(session, self._mutate)
            self.audits.append(audit)
            yield audit


async def second_connector(case: RuntimeCase) -> PersonalConnectionKey:
    from umbod.core.connectors.downstream_mcp.stores import SaveConnectorDefinition
    from umbod.core.connectors.downstream_mcp.personal_connections import ReplacePersonalAuthorization
    from umbod.core.connectors.downstream_mcp.personal_connections.authorization_models import authorize_personal_grant
    from umbod.core.connectors.downstream_mcp.stores.personal_oauth_configurations import install_personal_oauth_configuration
    from umbod.core.connectors.downstream_mcp.personal_oauth_configuration import PersonalOAuthSettings, PreconfiguredPublicOAuthClient
    from umbod.core.connectors.downstream_mcp.personal_tools import MissingInventoryRevision, SavePersonalToolObservation
    from umbod.core.permissions.stores.schema import CONNECTOR_PERMISSION_TABLE, GroupConnectorPermissionKey, GroupConnectorPermissionRecord

    definition = (await case.bundle.definitions.list()).definitions[0].model_copy(update={"connector_id": "second", "public_path": "/mcp/proxies/second", "display_name": "Second", "tool_name_prefix": "Second"})
    await case.bundle.definitions.save(SaveConnectorDefinition(definition=definition))
    await case.bundle.publishing.publish_connector("second")
    async with case.database.session(mode=TransactionMode.SERIALIZED_WRITE) as session:
        configuration = await install_personal_oauth_configuration(session, AuthenticatedTextCipher("runtime-secret"), "second", PersonalOAuthSettings(requested_scopes=case.grant.requested_scopes, client=PreconfiguredPublicOAuthClient(issuer_url="https://issuer.example", client_id="client")))
        await session.upsert(CONNECTOR_PERMISSION_TABLE, UpsertCommand(key=GroupConnectorPermissionKey(group_id="team", connector_id="second"), row=GroupConnectorPermissionRecord(group_id="team", connector_id="second")))
    key = PersonalConnectionKey(principal=case.query.key.principal, connector_id="second")
    await case.bundle.personal_connections.set_enabled(SetPersonalConnectionEnabled(key=key, enabled=True))
    connection = await case.bundle.personal_connections.get(key)
    grant = case.grant.model_copy(update={"key": key, "configuration_revision": configuration.policy.revision})
    await case.bundle.personal_connections.replace_authorization(ReplacePersonalAuthorization(key=key, expected_revision=connection.revision, authorization=authorize_personal_grant(grant)))
    query = case.query.model_copy(update={"key": key})
    target = await case.store.resolve(query)
    tool = approved_tool("read")
    tool = tool.model_copy(update={"identity": tool.identity.model_copy(update={"connector_id": "second"})})
    await case.bundle.personal_tool_access.save_observation(SavePersonalToolObservation(query=query, target=target, expected_inventory_revision=MissingInventoryRevision(kind="missing"), tools=(tool,), expires_at=target.expires_at))
    return key


@pytest.mark.asyncio
async def test_two_selected_connectors_share_snapshot_despite_interleaved_committed_disable(runtime_case: RuntimeCase) -> None:
    await save_matches(runtime_case, await replace_policy(runtime_case, (approved_tool("read"),)))
    key = await second_connector(runtime_case)

    async def disable_second() -> None:
        await runtime_case.bundle.personal_connections.set_enabled(SetPersonalConnectionEnabled(key=key, enabled=False))

    database = InterleavedDatabase(runtime_case, disable_second)
    reader = PersonalToolDiscoveryStore(database, AuthenticatedTextCipher("runtime-secret"))
    records = await reader.read(await discovery_query(runtime_case))
    assert {record.definition.connector_id for record in records} == {"personal", "second"}
    assert database.read_sessions == 1
    assert database.write_sessions == 0
    assert database.audits[0].reads == 4
    assert {record.definition.connector_id for record in await read_available(runtime_case.bundle, runtime_case.query)} == {"personal"}
