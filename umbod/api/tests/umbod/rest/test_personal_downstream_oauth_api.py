import asyncio
from typing import Literal

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tests.persistence_runtime import create_inmemory_runtime
from tests.umbod.core.downstream_mcp_connectors.adapters.test_oauth_service import MemoryHost
from umbod.core.connectors.downstream_mcp.models import OAuthConnectorDefinition
from umbod.core.connectors.downstream_mcp.oauth.ports import OAuthConnection
from umbod.core.connectors.downstream_mcp.oauth.service import OAuthService
from umbod.core.connectors.downstream_mcp.stores import (
    CONNECTOR_DEFINITION_TABLE,
    ConnectorDefinitionStore,
    ConnectorDefinitionStoreService,
    SaveConnectorDefinition,
)
from umbod.rest.connectors.downstream_mcp.dependencies import get_definition_store
from umbod.rest.connectors.downstream_mcp.oauth import get_oauth_service, router


class PersonalOAuthHost(MemoryHost):
    def connection(self, key: str) -> OAuthConnection:
        return OAuthConnection("https://alpha.example/mcp", "read", "personal")


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["details", "discover", "begin", "cancel", "refresh", "logout", "forget"])
async def test_shared_oauth_service_rejects_personal_ownership_before_mutation(operation: str) -> None:
    host = PersonalOAuthHost()
    service = OAuthService(host)
    authorization_before = host.saved.export()
    with pytest.raises(ValueError, match="Personal OAuth"):
        if operation == "begin":
            await service.begin("fixture", "", "write")
        else:
            await getattr(service, operation)("fixture")
    assert host.saved.export() == authorization_before
    assert host.scopes == "read"
    assert host.reconnections == 0
    assert service.results == {}
    assert service.events == {}
    assert service.tasks == {}
    await service.close()


@pytest.mark.asyncio
async def test_shared_oauth_callback_does_not_complete_personal_attempt() -> None:
    service = OAuthService(PersonalOAuthHost())
    callback = asyncio.get_running_loop().create_future()
    service.callbacks["fixture"] = callback
    service.expected_states["fixture"] = "expected"
    result = await service.callback("fixture", {"state": "expected", "code": "code-canary"})
    assert result.status_code == 400
    assert not callback.done()
    callback.cancel()
    await service.close()


@pytest.mark.parametrize("method,operation", [
    ("GET", ""), ("POST", "/discover"), ("POST", "/begin"),
    ("POST", "/cancel"), ("POST", "/refresh"), ("POST", "/logout"),
])
def test_admin_oauth_api_rejects_persisted_personal_definition(
    method: Literal["GET", "POST"], operation: str,
) -> None:
    definitions: ConnectorDefinitionStore = ConnectorDefinitionStoreService(
        create_inmemory_runtime().database, CONNECTOR_DEFINITION_TABLE
    )
    asyncio.run(definitions.save(SaveConnectorDefinition(definition=OAuthConnectorDefinition(
        connector_id="fixture", display_name="Fixture", endpoint_url="https://alpha.example/mcp",
        authorization_mode="personal",
    ))))
    service = OAuthService(MemoryHost())
    app = FastAPI()
    app.include_router(router, prefix="/api/admin")
    app.dependency_overrides[get_definition_store] = lambda: definitions
    app.dependency_overrides[get_oauth_service] = lambda: service
    with TestClient(app) as client:
        response = client.request(method, "/api/admin/connectors/mcp/oauth/fixture" + operation, json={})
    assert response.status_code == 409
    assert response.json() == {"detail": {"code": "personal_oauth_unavailable"}}
    assert service.results == {}
    assert service.tasks == {}
    assert service.events == {}
