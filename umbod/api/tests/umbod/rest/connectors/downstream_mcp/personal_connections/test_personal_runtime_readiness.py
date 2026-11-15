from datetime import timedelta

import pytest
from pydantic import SecretStr

from tests.umbod.core.connectors.downstream_mcp.personal_discovery_support import read_available
from umbod.core.connectors.downstream_mcp.adapters.personal_runtime import InMemoryPersonalMcpTransport
from umbod.core.connectors.downstream_mcp.models import DiscoveredToolWithoutOutputSchema, ToolIdentity
from umbod.core.connectors.downstream_mcp.personal_connections import Authorized, ReplacePersonalAuthorization
from umbod.core.connectors.downstream_mcp.personal_connections.authorization_models import PersonalOAuthGrant, PresentPersonalRefreshToken, authorize_personal_grant
from umbod.core.connectors.downstream_mcp.personal_connections.health_models import RejectPersonalAuthorization
from umbod.core.connectors.downstream_mcp.personal_connections.refresh_models import FailPersonalRefresh, PersonalRefreshCommand, ReservePersonalRefresh
from umbod.core.connectors.downstream_mcp.personal_connections.runtime_models import PersonalToolInventory
from umbod.core.connectors.downstream_mcp.personal_oauth_configuration import PersonalOAuthConfigurationQuery, PersonalOAuthSettings, PreconfiguredPublicOAuthClient, ReplacePersonalOAuthConfiguration
from umbod.core.connectors.downstream_mcp.stores import DownstreamMcpStores
from umbod.rest.connectors.downstream_mcp.personal_connections.discovery import PersonalConnectorDiscovery, get_personal_connector_discovery
from umbod.rest.connectors.downstream_mcp.personal_connections.tools import get_personal_tool_transport

from .test_personal_tool_discovery import DiscoveryApi, discovery_api, query, stores_with_grants

__all__ = ["discovery_api"]


async def configure_renewable_grant(api: DiscoveryApi, stores: DownstreamMcpStores) -> None:
    configuration = await stores.personal_oauth_configurations.get(PersonalOAuthConfigurationQuery(connector_id=api.connector_id))
    previous = await stores.personal_connections.get(query(api, "alice").key)
    assert isinstance(previous.authorization, Authorized)
    parsed = PersonalOAuthGrant.model_validate_json(previous.authorization.authorization.get_secret_value())
    replaced = await stores.personal_oauth_configurations.replace(ReplacePersonalOAuthConfiguration(connector_id=api.connector_id, expected_revision=configuration.policy.revision, settings=PersonalOAuthSettings(requested_scopes=(), client=PreconfiguredPublicOAuthClient(issuer_url="https://issuer.example", client_id="public-client"))))
    connection = await stores.personal_connections.get(query(api, "alice").key)
    grant = parsed.model_copy(update={"configuration_revision": replaced.policy.revision, "client_mode": "preconfigured_public", "refresh_token": PresentPersonalRefreshToken(token=SecretStr("readiness-refresh-token"))})
    await stores.personal_connections.replace_authorization(ReplacePersonalAuthorization(key=connection.key, expected_revision=connection.revision, authorization=authorize_personal_grant(grant)))


async def change_readiness(api: DiscoveryApi, stores: DownstreamMcpStores, state: str) -> None:
    current_query = query(api, "alice")
    connection = await stores.personal_connections.get(current_query.key)
    if state == "rejected":
        await stores.personal_tool_access.reject_authorization(RejectPersonalAuthorization(key=current_query.key, expected_connection_revision=connection.revision))
    elif state == "replacement":
        assert isinstance(connection.authorization, Authorized)
        grant = PersonalOAuthGrant.model_validate_json(connection.authorization.authorization.get_secret_value()).model_copy(update={"access_token": SecretStr("replacement-readiness-token")})
        await stores.personal_connections.replace_authorization(ReplacePersonalAuthorization(key=connection.key, expected_revision=connection.revision, authorization=authorize_personal_grant(grant)))
    elif state != "expired":
        await stores.personal_refresh.reserve(ReservePersonalRefresh(key=current_query.key, group_ids=current_query.group_ids, claim_id="readiness", now=current_query.now))
        if state != "preparing":
            command = PersonalRefreshCommand(key=current_query.key, claim_id="readiness", now=query(api, "alice").now)
            await stores.personal_refresh.exchange(command)
            if state in ("refresh_denied", "refresh_uncertain"):
                await stores.personal_refresh.fail(FailPersonalRefresh(**command.model_dump(), reason=state))


@pytest.mark.parametrize("state", ["expired", "rejected", "preparing", "exchanging", "refresh_denied", "refresh_uncertain", "replacement"])
def test_runtime_available_uses_executable_readiness_not_retained_descriptors(discovery_api: DiscoveryApi, state: str) -> None:
    api = discovery_api
    stores = api.client.portal.call(stores_with_grants, api)
    api.client.portal.call(configure_renewable_grant, api, stores)
    transport = InMemoryPersonalMcpTransport()
    observed = DiscoveredToolWithoutOutputSchema(identity=ToolIdentity(connector_id=api.connector_id, downstream_name="lookup"), title="Private lookup", description="Private owner descriptor", input_schema={"type": "object"})
    transport.inventories[query(api, "alice").key] = PersonalToolInventory(tools=(observed,))

    def provide_transport() -> InMemoryPersonalMcpTransport:
        return transport

    api.personal_app.dependency_overrides[get_personal_tool_transport] = provide_transport
    headers = api.headers("alice")
    api.client.post(api.url + "/tools/discovery", headers=headers, json={}).raise_for_status()
    assert api.client.get(api.url, headers=headers).json()["runtime_available"] is True
    api.client.portal.call(change_readiness, api, stores, state)
    now = query(api, "alice").now + (timedelta(hours=2) if state == "expired" else timedelta())

    def provide_readiness() -> PersonalConnectorDiscovery:
        return PersonalConnectorDiscovery(stores.personal_tool_discovery, stores.definitions, query(api, "alice").key.principal, True, lambda: now)

    api.personal_app.dependency_overrides[get_personal_connector_discovery] = provide_readiness
    expected_query = query(api, "alice").model_copy(update={"now": now})
    assert len(api.client.portal.call(read_available, stores, expected_query)) == 1
    assert api.client.get(api.url, headers=headers).json()["runtime_available"] is False
    selections = api.client.get("/api/me/connectors/mcp", headers=headers).json()["connectors"]
    assert next(item for item in selections if item["connector_id"] == api.connector_id)["runtime_available"] is False
    assert len(transport.list_requests) == 1
    assert transport.calls == []
    if state == "replacement":
        api.client.post(api.url + "/tools/discovery", headers=headers, json={}).raise_for_status()
        assert api.client.get(api.url, headers=headers).json()["runtime_available"] is True
        assert len(transport.list_requests) == 2
        assert transport.calls == []
