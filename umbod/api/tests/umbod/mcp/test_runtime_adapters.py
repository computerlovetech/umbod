from unittest.mock import Mock

import pytest

from tests.persistence_runtime import create_inmemory_runtime
from umbod.core.connectors.downstream_mcp.adapters import composition
from umbod.core.connectors.downstream_mcp.models import NoAuthCredentialState
from umbod.core.connectors.downstream_mcp.stores import ConnectorIdQuery, CredentialFound, SaveCredential, create_downstream_mcp_stores
from umbod.mcp.runtime_adapters import create_configured_downstream_client_factory
from umbod.mcp.settings import MCPAppSettings


@pytest.mark.asyncio
@pytest.mark.parametrize("oauth_enabled", [False, True])
async def test_configured_downstream_factory_preserves_options_and_shared_credentials(
    monkeypatch: pytest.MonkeyPatch, oauth_enabled: bool,
) -> None:
    persistence = create_inmemory_runtime()
    await persistence.readiness.ensure_ready()
    settings = MCPAppSettings(connector_security={'configuration_secret': 'adapter-secret'}, mcp={'downstream_oauth_enabled': oauth_enabled})
    connection_constructor = Mock()
    monkeypatch.setattr(composition, "FastMCPDownstreamConnectionFactory", connection_constructor)
    try:
        first = await create_configured_downstream_client_factory(settings, persistence.database)
        second = await create_configured_downstream_client_factory(settings, persistence.database)
        assert first is not second
        assert connection_constructor.call_count == 2
        for call in connection_constructor.call_args_list:
            assert call.args[0] is True
            assert call.kwargs == {'oauth_enabled': oauth_enabled}
        credentials = connection_constructor.call_args_list[0].args[1]
        credential = NoAuthCredentialState(connector_id='configured-adapter')
        await credentials.save(SaveCredential(credential=credential))
        stores = await create_downstream_mcp_stores('adapter-secret', persistence.database)
        found = await stores.credentials.get(ConnectorIdQuery(connector_id='configured-adapter'))
        assert isinstance(found, CredentialFound)
        assert found.credential == credential
        connection_constructor.return_value.create.assert_not_called()
    finally:
        await persistence.shutdown()
