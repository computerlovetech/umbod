from umbod.core.connectors.downstream_mcp.adapters.settings import DownstreamMcpInfrastructureSettings

from umbod.core.connectors.downstream_mcp.stores import create_downstream_mcp_stores
from umbod.infrastructure.persistence.schema_preparation import prepare_application_schema
from umbod.infrastructure.persistence.sqlite.database import SQLiteDatabase
from pathlib import Path
import pytest

def infrastructure_settings() -> DownstreamMcpInfrastructureSettings:
    return DownstreamMcpInfrastructureSettings(credential_secret='test-credential-secret', tls_verification=True, connection_timeout_seconds=10.0, discovery_timeout_seconds=17.0)

@pytest.mark.asyncio
async def test_store_composition_creates_request_owned_bundles(tmp_path: Path) -> None:
    settings = infrastructure_settings()
    database = SQLiteDatabase(str(tmp_path / 'connectors.sqlite3'), create_parent_dirs=True)
    await prepare_application_schema(database)
    first_stores = await create_downstream_mcp_stores(settings.credential_secret, database)
    second_stores = await create_downstream_mcp_stores(settings.credential_secret, database)
    assert first_stores is not second_stores
    assert first_stores.definitions is not second_stores.definitions
    assert first_stores.definitions._database is database
    assert first_stores.credentials._database is database
    assert first_stores.catalogs._database is database
    assert first_stores.health._database is database
