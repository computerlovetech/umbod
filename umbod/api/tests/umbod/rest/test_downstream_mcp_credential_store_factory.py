import pytest

from umbod.infrastructure import ConfiguredPersistenceRuntimeProvider
from umbod.core.connectors.downstream_mcp.models import StaticBearerCredentialState
from umbod.core.connectors.downstream_mcp.stores import ConnectorIdQuery, CredentialFound, SaveCredential
from umbod.rest.factories import ConfiguredDownstreamMcpCredentialStoreFactory
from umbod.rest.settings import APISettings

@pytest.mark.parametrize('configured_secret', ['', 'explicit-secret'])
@pytest.mark.asyncio
async def test_rest_written_credential_is_readable_by_runtime_store(configured_secret: str) -> None:
    settings = APISettings(
        connector_store={'type': 'inmemory'},
        connector_security={'configuration_secret': configured_secret},
    )
    runtime = ConfiguredPersistenceRuntimeProvider(settings.connector_store).create()
    try:
        await runtime.readiness.ensure_ready()
        api_store = ConfiguredDownstreamMcpCredentialStoreFactory(settings, runtime.database).create()
        await api_store.save(SaveCredential(credential=StaticBearerCredentialState(connector_id='alpha', bearer_token='bearer-secret')))
        runtime_store = ConfiguredDownstreamMcpCredentialStoreFactory(settings, runtime.database).create()
        assert api_store is not runtime_store
        result = await runtime_store.get(ConnectorIdQuery(connector_id='alpha'))
        assert isinstance(result, CredentialFound)
        assert isinstance(result.credential, StaticBearerCredentialState)
        assert result.credential.bearer_token.get_secret_value() == 'bearer-secret'
    finally:
        await runtime.shutdown()

@pytest.mark.asyncio
async def test_inmemory_downstream_stores_share_application_runtime_state() -> None:
    settings = APISettings(connector_store={'type': 'inmemory'})
    runtime = ConfiguredPersistenceRuntimeProvider(settings.connector_store).create()
    try:
        await runtime.readiness.ensure_ready()
        first_store = ConfiguredDownstreamMcpCredentialStoreFactory(settings, runtime.database).create()
        second_store = ConfiguredDownstreamMcpCredentialStoreFactory(settings, runtime.database).create()
        assert first_store is not second_store
        await first_store.save(SaveCredential(credential=StaticBearerCredentialState(connector_id='alpha', bearer_token='bearer-secret')))
        result = await second_store.get(ConnectorIdQuery(connector_id='alpha'))
        assert isinstance(result, CredentialFound)
    finally:
        await runtime.shutdown()
