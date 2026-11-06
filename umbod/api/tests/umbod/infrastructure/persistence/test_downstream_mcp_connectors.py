import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

import pytest
from pydantic import SecretStr

from umbod.core.configuration.persistence import AuthenticatedTextCipher
from umbod.core.connectors.downstream_mcp.personal_connections import (
    Authorized, CanonicalPrincipal, PersonalConnection, PersonalConnectionKey,
    ReplacePersonalAuthorization, SetPersonalConnectionEnabled,
)
from umbod.core.connectors.downstream_mcp.stores.personal_connections import EncryptedPersonalConnectionStore
from umbod.core.persistence import AllFields, NoFilter, Query, Unordered
from umbod.core.connectors.downstream_mcp.stores.schema import PERSONAL_CONNECTION_TABLE
from umbod.core.connectors.downstream_mcp.adapters.settings import DownstreamMcpInfrastructureSettings
from umbod.core.connectors.downstream_mcp.models import (
    ConnectorHealthy,
    DiscoveredToolWithoutOutputSchema,
    OAuthCredentialState,
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
from umbod.infrastructure.persistence.sqlite.factories import create_unpooled_sqlite_database


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
    database = create_unpooled_sqlite_database(database_path, create_parent_dirs=True)
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
    with closing(sqlite3.connect(database_path)) as connection:
        stored = connection.execute(
            'SELECT document FROM downstream_mcp_connector_credentials WHERE connector_id = ?',
            (credential.connector_id,),
        ).fetchone()
    assert stored is not None
    assert credential.bearer_token.get_secret_value() not in stored[0]
    await first_stores.catalogs.replace(ReplaceToolCatalog(snapshot=snapshot))
    await first_stores.health.save(SaveConnectorHealth(health=health))

    reopened_database = create_unpooled_sqlite_database(database_path, create_parent_dirs=False)
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


@pytest.mark.asyncio
async def test_oauth_credentials_remain_encrypted_across_database_instances(tmp_path: Path) -> None:
    path = tmp_path / "oauth.sqlite3"
    database = create_unpooled_sqlite_database(str(path), create_parent_dirs=True)
    await prepare_application_schema(database)
    stores = await create_downstream_mcp_stores("oauth-test-key", database)
    credential = OAuthCredentialState(
        connector_id="oauth-connector",
        authorization=SecretStr('{"access_token":"old-access","refresh_token":"old-refresh"}'),
    )
    await stores.credentials.save(SaveCredential(credential=credential))
    with closing(sqlite3.connect(path)) as connection:
        stored = connection.execute(
            'SELECT document FROM downstream_mcp_connector_credentials WHERE connector_id = ?',
            (credential.connector_id,),
        ).fetchone()
    assert stored is not None
    assert "old-access" not in stored[0]
    assert "old-refresh" not in stored[0]
    assert b"old-access" not in path.read_bytes()
    assert b"old-refresh" not in path.read_bytes()
    reopened_database = create_unpooled_sqlite_database(str(path), create_parent_dirs=False)
    reopened = await create_downstream_mcp_stores("oauth-test-key", reopened_database)
    assert await reopened.credentials.get(ConnectorIdQuery(connector_id=credential.connector_id)) == CredentialFound(credential=credential)


@pytest.mark.asyncio
async def test_personal_authorization_remains_encrypted_across_database_instances(tmp_path: Path) -> None:
    path = tmp_path / "personal.sqlite3"
    database = create_unpooled_sqlite_database(str(path), create_parent_dirs=True)
    await prepare_application_schema(database)
    store = EncryptedPersonalConnectionStore(database, AuthenticatedTextCipher("personal-test-key"))
    key = PersonalConnectionKey(
        principal=CanonicalPrincipal(namespace="trusted", subject="owner"), connector_id="alpha",
    )
    current = await store.set_enabled(SetPersonalConnectionEnabled(key=key, enabled=True))
    assert isinstance(current, PersonalConnection)
    expected = await store.replace_authorization(ReplacePersonalAuthorization(
        key=key, expected_revision=current.revision,
        authorization=Authorized(authorization="never-plaintext-authorization"),
    ))
    with closing(sqlite3.connect(path)) as connection:
        stored = connection.execute(
            'SELECT document FROM downstream_mcp_personal_connections '
            'WHERE namespace = ? AND subject = ? AND connector_id = ?',
            (key.principal.namespace, key.principal.subject, key.connector_id),
        ).fetchone()
    assert stored is not None
    assert "never-plaintext-authorization" not in stored[0]
    assert "never-plaintext-authorization".encode() not in path.read_bytes()
    reopened_database = create_unpooled_sqlite_database(str(path), create_parent_dirs=False)
    async with reopened_database.read_session() as session:
        row = await session.find_one(PERSONAL_CONNECTION_TABLE, Query(NoFilter(), AllFields(), Unordered()))
    assert row is not None
    assert row.document == stored[0]
    restored = EncryptedPersonalConnectionStore(reopened_database, AuthenticatedTextCipher("personal-test-key"))
    assert await restored.get(key) == expected
