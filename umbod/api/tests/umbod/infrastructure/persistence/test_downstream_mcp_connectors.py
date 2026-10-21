from datetime import datetime, timezone
from pathlib import Path

import pytest
from pydantic import SecretStr

from umbod.core.connectors.downstream_mcp.adapters.settings import DownstreamMcpInfrastructureSettings
from umbod.core.connectors.downstream_mcp.models import (
    ConnectorHealthy,
    DiscoveredToolWithoutOutputSchema,
    StaticBearerConnectorDefinition,
    StaticBearerCredentialState,
    ToolCatalogSnapshot,
    ToolIdentity,
)
from umbod.core.connectors.downstream_mcp.stores import (
    ConnectorDefinitionFound,
    ConnectorHealthFound,
    ConnectorIdQuery,
    CredentialFound,
    ReplaceToolCatalog,
    SaveConnectorDefinition,
    SaveConnectorHealth,
    SaveCredential,
    ToolCatalogFound,
    create_downstream_mcp_stores,
)
from umbod.infrastructure.persistence.schema_preparation import prepare_application_schema
from umbod.infrastructure.persistence.sqlite.database import SQLiteDatabase


def infrastructure_settings() -> DownstreamMcpInfrastructureSettings:
    return DownstreamMcpInfrastructureSettings(
        credential_secret="test-credential-secret",
        tls_verification=True,
        connection_timeout_seconds=10.0,
        discovery_timeout_seconds=17.0,
    )


@pytest.mark.asyncio
async def test_store_composition_creates_request_owned_bundles(tmp_path: Path) -> None:
    settings = infrastructure_settings()
    database_path = str(tmp_path / "connectors.sqlite3")
    database = SQLiteDatabase(database_path, create_parent_dirs=True)
    await prepare_application_schema(database)
    first_stores = await create_downstream_mcp_stores(settings.credential_secret, database)
    second_stores = await create_downstream_mcp_stores(settings.credential_secret, database)
    assert first_stores is not second_stores
    assert first_stores.definitions is not second_stores.definitions
    assert first_stores.credentials is not second_stores.credentials
    assert first_stores.catalogs is not second_stores.catalogs
    assert first_stores.health is not second_stores.health

    query = ConnectorIdQuery(connector_id="shared-connector")
    definition = StaticBearerConnectorDefinition(
        connector_id=query.connector_id,
        display_name="Shared Connector",
        tool_name_prefix="shared",
        capability_description="Shared connector capabilities",
        endpoint_url="https://api.example.test/mcp",
        public_path="/mcp/proxies/shared-connector",
    )
    credential = StaticBearerCredentialState(
        connector_id=query.connector_id,
        bearer_token=SecretStr("persisted-credential-canary"),
    )
    checked_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    snapshot = ToolCatalogSnapshot(
        connector_id=query.connector_id,
        discovered_at=checked_at,
        tools=(
            DiscoveredToolWithoutOutputSchema(
                identity=ToolIdentity(
                    connector_id=query.connector_id, downstream_name="shared-tool"
                ),
                title="Shared Tool",
                description="Persisted tool",
                input_schema={"type": "object"},
            ),
        ),
    )
    health = ConnectorHealthy(connector_id=query.connector_id, checked_at=checked_at)

    await first_stores.definitions.save(SaveConnectorDefinition(definition=definition))
    await first_stores.credentials.save(SaveCredential(credential=credential))
    await first_stores.catalogs.replace(ReplaceToolCatalog(snapshot=snapshot))
    await first_stores.health.save(SaveConnectorHealth(health=health))

    reopened_database = SQLiteDatabase(database_path, create_parent_dirs=False)
    third_stores = await create_downstream_mcp_stores(
        settings.credential_secret, reopened_database
    )
    for stores in (second_stores, third_stores):
        assert await stores.definitions.get(query) == ConnectorDefinitionFound(
            definition=definition
        )
        assert await stores.credentials.get(query) == CredentialFound(credential=credential)
        assert await stores.catalogs.get(query) == ToolCatalogFound(snapshot=snapshot)
        assert await stores.health.get(query) == ConnectorHealthFound(health=health)
