from datetime import UTC, datetime

from fastapi import FastAPI
from fastapi.testclient import TestClient

from umbod.core.connectors.downstream_mcp.personal_oauth_setup.models import DiscoverPersonalOAuthSetup, PersonalOAuthSetupDiscovery, PersonalOAuthSetupValidation, ValidatePersonalOAuthSetup, ValidatedPersonalOAuthSetup
from umbod.core.connectors.downstream_mcp.personal_oauth_setup.state import CompletePersonalOAuthSetup, PersonalOAuthSetupQuery, SetupValidated, StartPersonalOAuthSetup
from umbod.core.connectors.downstream_mcp.stores import DownstreamMcpStores
from umbod.core.connectors.downstream_mcp.personal_oauth_setup.ports import PersonalOAuthSetupStore
from umbod.rest.connectors.downstream_mcp.personal_oauth_setup import get_setup_provider


SETUP_CALLBACK = "https://umbod.example/api/oauth/downstream-mcp/callback"


class SuccessfulSetupProvider:
    async def discover(self, command: DiscoverPersonalOAuthSetup) -> PersonalOAuthSetupDiscovery:
        return PersonalOAuthSetupDiscovery(issuer_url="https://issuer.example", redirect_uri=command.redirect_uri, available_scopes=(), registration_mode=command.policy.client.kind)

    async def validate(self, command: ValidatePersonalOAuthSetup) -> PersonalOAuthSetupValidation:
        return ValidatedPersonalOAuthSetup(discovery=await self.discover(command), returned_scopes=(), scope_source="not_checked")


def install_api_setup_validation(client: TestClient, headers: dict[str, str], connector_id: str) -> None:
    app = client.app
    if not isinstance(app, FastAPI):
        raise TypeError("Expected API application")
    admin = next(route.app for route in app.routes if getattr(route, "path", "") == "/api/admin")
    admin.dependency_overrides[get_setup_provider] = SuccessfulSetupProvider
    url = f"/api/admin/connectors/mcp/{connector_id}/personal-oauth/setup"
    status = client.get(url, headers=headers)
    status.raise_for_status()
    result = client.post(url + "/validation", headers=headers, json={"expected_revision": status.json()["revision"]})
    result.raise_for_status()
    if result.json()["state"]["status"] != "validated":
        raise ValueError("Fixture setup validation failed")


async def install_setup_validation(stores: DownstreamMcpStores, connector_id: str, redirect_uri: str = SETUP_CALLBACK) -> None:
    await install_store_setup_validation(stores.personal_oauth_setup, connector_id, redirect_uri)


async def install_store_setup_validation(store: PersonalOAuthSetupStore, connector_id: str, redirect_uri: str = SETUP_CALLBACK) -> None:
    query = PersonalOAuthSetupQuery(connector_id=connector_id, redirect_uri=redirect_uri)
    status = await store.get(query)
    started = await store.start(StartPersonalOAuthSetup(**query.model_dump(), operation="validation", expected_revision=status.revision))
    result = await SuccessfulSetupProvider().validate(ValidatePersonalOAuthSetup(endpoint_url=started.endpoint_url, redirect_uri=redirect_uri, policy=started.policy))
    if not isinstance(result, ValidatedPersonalOAuthSetup):
        raise TypeError("Expected validated fixture")
    await store.complete(CompletePersonalOAuthSetup(started=started, state=SetupValidated(result=result, checked_at=datetime.now(UTC))))
