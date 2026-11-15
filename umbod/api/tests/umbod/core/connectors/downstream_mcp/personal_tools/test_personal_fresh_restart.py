import json
from datetime import timedelta

import pytest
from pydantic import SecretStr

from tests.umbod.core.connectors.downstream_mcp.personal_discovery_support import read_available
from tests.umbod.core.connectors.downstream_mcp.test_personal_runtime_authorizations import RuntimeCase, install_authorization, runtime_case
from umbod.core.configuration.persistence import AuthenticatedTextCipher
from umbod.core.connectors.downstream_mcp.personal_connections.authorization_models import authorize_personal_grant
from umbod.core.connectors.downstream_mcp.personal_connections.health_models import RejectPersonalAuthorization
from umbod.core.connectors.downstream_mcp.personal_connections.runtime_models import PersonalAuthorizationRequired, PersonalRuntimeUnavailable
from umbod.core.connectors.downstream_mcp.personal_tools import PersonalToolDiscoveryQuery, PersonalToolDiscoveryService, PersonalToolRuntimeService
from umbod.core.connectors.downstream_mcp.stores.personal_discovery_projection import DISCOVERY_AVAILABILITY_ADAPTER, AvailableDiscovery, discovery_filter
from umbod.core.connectors.downstream_mcp.stores.personal_discovery_schema import PERSONAL_DISCOVERY_TABLE
from umbod.core.connectors.downstream_mcp.stores.queries import query_all
from umbod.core.connectors.downstream_mcp.stores.schema import PersonalConnectionRecordKey
from umbod.core.persistence import TransactionMode, UpsertCommand

from .runtime_support import execution_case
from .test_personal_inventory import observation_row, replace_document

__all__ = ["runtime_case"]


@pytest.mark.asyncio
@pytest.mark.parametrize("projection_format", ["current", "unsupported"])
@pytest.mark.parametrize("block", ["expired", "rejected"])
async def test_reauthentication_and_fresh_discovery_replace_unsupported_persistence_before_recovery(runtime_case: RuntimeCase, projection_format: str, block: str) -> None:
    execution = await execution_case(runtime_case)
    cipher = AuthenticatedTextCipher("runtime-secret")
    document = json.loads(cipher.decrypt((await observation_row(runtime_case)).document))
    document["version"] = 2
    await replace_document(runtime_case, cipher.encrypt(json.dumps(document)))
    if projection_format == "unsupported":
        async with runtime_case.database.session(mode=TransactionMode.SERIALIZED_WRITE) as session:
            row = await session.find_one(PERSONAL_DISCOVERY_TABLE, query_all(discovery_filter(runtime_case.query.key)))
            assert row is not None
            projection = json.loads(cipher.decrypt(row.document))
            for field in ("version", "expected_authorization_revision", "authorization_rejected"):
                projection.pop(field)
            key = PersonalConnectionRecordKey(namespace=row.namespace, subject=row.subject, connector_id=row.connector_id)
            await session.upsert(PERSONAL_DISCOVERY_TABLE, UpsertCommand(key=key, row=row.model_copy(update={"document": cipher.encrypt(json.dumps(projection))})))
    assert await read_available(runtime_case.bundle, runtime_case.query) == ()
    grant = runtime_case.grant.model_copy(update={"access_token": SecretStr("fresh-restart-token")})
    await install_authorization(runtime_case, authorize_personal_grant(grant))
    async with runtime_case.database.read_session() as session:
        row = await session.find_one(PERSONAL_DISCOVERY_TABLE, query_all(discovery_filter(runtime_case.query.key)))
        assert row is not None
        projection = DISCOVERY_AVAILABILITY_ADAPTER.validate_json(cipher.decrypt(row.document))
    assert isinstance(projection, AvailableDiscovery)
    assert projection.version == 2
    assert await read_available(runtime_case.bundle, runtime_case.query) == ()
    with pytest.raises(PersonalRuntimeUnavailable) as unavailable:
        await execution.runtime.execute(execution.command)
    assert not isinstance(unavailable.value, PersonalAuthorizationRequired)
    discovery = PersonalToolDiscoveryService(runtime_case.store, runtime_case.bundle.personal_tool_access, execution.transport, lambda: runtime_case.query.now)
    await discovery.discover(runtime_case.query)
    assert json.loads(cipher.decrypt((await observation_row(runtime_case)).document))["version"] == 3
    records = await read_available(runtime_case.bundle, runtime_case.query)
    assert len(records) == 1
    now = runtime_case.query.now
    if block == "expired":
        now += timedelta(hours=2)
    else:
        connection = await runtime_case.bundle.personal_connections.get(runtime_case.query.key)
        await runtime_case.bundle.personal_tool_access.reject_authorization(RejectPersonalAuthorization(key=runtime_case.query.key, expected_connection_revision=connection.revision))
    query = runtime_case.query.model_copy(update={"now": now})
    assert await read_available(runtime_case.bundle, query) == records
    definitions = (await runtime_case.bundle.definitions.list()).definitions
    assert await runtime_case.bundle.personal_tool_discovery.read_available(PersonalToolDiscoveryQuery(principal=query.key.principal, definitions=definitions, now=now)) == ()
    runtime = PersonalToolRuntimeService(execution.caller, runtime_case.bundle.personal_tool_access, execution.transport, lambda: now)
    with pytest.raises(PersonalAuthorizationRequired) as required:
        await runtime.execute(execution.command.model_copy(update={"inventory_revision": records[0].inventory_revision}))
    assert required.value.reason == block
    assert execution.transport.calls == []
    assert len(execution.transport.list_requests) == 1
