import asyncio

import pytest

from tests.umbod.core.downstream_mcp_connectors.personal_discovery_audit import AuditedDatabase, RestrictedCipher
from tests.umbod.core.downstream_mcp_connectors.personal_discovery_support import read_available
from tests.umbod.core.downstream_mcp_connectors.test_personal_runtime_authorizations import RuntimeCase, runtime_case
from tests.umbod.core.downstream_mcp_connectors.test_personal_tools_s3_contracts import approved_tool, replace_policy, save_matches
from umbod.core.configuration.persistence import AuthenticatedTextCipher
from umbod.core.connectors.downstream_mcp.personal_connections import SetPersonalConnectionEnabled
from umbod.core.connectors.downstream_mcp.stores.personal_discovery_schema import PERSONAL_DISCOVERY_TABLE
from umbod.core.persistence import DeleteQuery, NoFilter, TransactionMode
from umbod.infrastructure import PersonalDiscoveryPreparation

__all__ = ["runtime_case"]


async def remove_projection(case: RuntimeCase) -> None:
    async with case.database.session(mode=TransactionMode.SERIALIZED_WRITE) as session:
        await session.delete(PERSONAL_DISCOVERY_TABLE, DeleteQuery(NoFilter()))


@pytest.mark.asyncio
async def test_legacy_observations_survive_concurrent_backfill_and_repeat_preparation_without_writers(runtime_case: RuntimeCase) -> None:
    await save_matches(runtime_case, await replace_policy(runtime_case, (approved_tool("private"),)))
    previous = await read_available(runtime_case.bundle, runtime_case.query)
    await remove_projection(runtime_case)
    assert await read_available(runtime_case.bundle, runtime_case.query) == ()
    database = AuditedDatabase(runtime_case.database, discovery_only=False)
    cipher = AuthenticatedTextCipher("runtime-secret")
    await asyncio.gather(PersonalDiscoveryPreparation(database, cipher).prepare(), PersonalDiscoveryPreparation(database, cipher).prepare())
    assert await read_available(runtime_case.bundle, runtime_case.query) == previous
    assert database.write_sessions <= 2
    database.write_sessions = 0
    forbidden_cipher = RestrictedCipher(cipher, frozenset())
    await PersonalDiscoveryPreparation(database, forbidden_cipher).prepare()
    assert database.write_sessions == 0
    assert forbidden_cipher.decryptions == 0


@pytest.mark.asyncio
async def test_backfill_and_concurrent_disable_never_restore_stale_availability(runtime_case: RuntimeCase) -> None:
    await save_matches(runtime_case, await replace_policy(runtime_case, (approved_tool("read"),)))
    await remove_projection(runtime_case)
    await asyncio.gather(
        PersonalDiscoveryPreparation(runtime_case.database, AuthenticatedTextCipher("runtime-secret")).prepare(),
        runtime_case.bundle.personal_connections.set_enabled(SetPersonalConnectionEnabled(key=runtime_case.query.key, enabled=False)),
    )
    assert await read_available(runtime_case.bundle, runtime_case.query) == ()
