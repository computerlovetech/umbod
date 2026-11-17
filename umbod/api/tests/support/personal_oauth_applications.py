from collections.abc import Callable
from datetime import UTC, datetime
from uuid import uuid4
from pydantic import SecretStr

from umbod.core.persistence import Database, TransactionMode
from umbod.core.configuration.persistence import AuthenticatedTextCipher
from umbod.core.connectors.downstream_mcp.models import OAuthConnectorDefinition
from umbod.core.connectors.downstream_mcp.personal_oauth_configuration import PersonalOAuthSettings, DynamicConfidentialOAuthClient
from umbod.core.connectors.downstream_mcp.stores import SaveConnectorDefinition, create_downstream_mcp_stores
from umbod.core.connectors.downstream_mcp.stores.personal_oauth_configurations import install_personal_oauth_configuration

from umbod.core.connectors.downstream_mcp.personal_oauth_applications.models import (
    ClaimedOAuthApplication, CompleteOAuthApplication, ExpiringApplicationSecret,
    OAuthApplicationBinding, OAuthApplicationUnavailable, ReadyOAuthApplication, ResolveOAuthApplication,
    OAuthApplicationCredentials, NonexpiringApplicationSecret,
)


async def install_application_policy(database: Database) -> OAuthApplicationBinding:
    stores = await create_downstream_mcp_stores("test-secret", database)
    definition = OAuthConnectorDefinition(connector_id="connector", display_name="Personal", endpoint_url="https://resource.example/mcp", authorization_mode="personal")
    await stores.definitions.save(SaveConnectorDefinition(definition=definition))
    async with database.session(mode=TransactionMode.SERIALIZED_WRITE) as session:
        configuration = await install_personal_oauth_configuration(
            session, AuthenticatedTextCipher("test-secret"), "connector",
            PersonalOAuthSettings(requested_scopes=(), client=DynamicConfidentialOAuthClient(token_endpoint_auth_method="client_secret_basic")),
        )
    return OAuthApplicationBinding(
        connector_id="connector", configuration_revision=configuration.policy.revision,
        issuer="https://issuer.example", resource=definition.endpoint_url,
        redirect_uri="https://umbod.example/callback", token_endpoint="https://issuer.example/token",
        requested_scopes=(), token_endpoint_auth_method="client_secret_basic",
    )


def application_credentials() -> OAuthApplicationCredentials:
    return OAuthApplicationCredentials(client_id="registered-client", client_secret=SecretStr("private-registered-secret-sentinel"), lifetime=NonexpiringApplicationSecret())


def application_clock() -> datetime:
    return datetime.now(UTC)


class InMemoryPersonalOAuthApplicationStore:
    def __init__(self, clock: Callable[[], datetime]) -> None:
        self._clock = clock
        self.applications: dict[str, ClaimedOAuthApplication | ReadyOAuthApplication] = {}

    def _valid(self, application: ReadyOAuthApplication) -> bool:
        lifetime = application.credentials.lifetime
        return not isinstance(lifetime, ExpiringApplicationSecret) or lifetime.expires_at > self._clock()

    async def reserve(self, binding: OAuthApplicationBinding) -> ClaimedOAuthApplication | ReadyOAuthApplication:
        for application in self.applications.values():
            if application.binding != binding:
                continue
            if isinstance(application, ClaimedOAuthApplication):
                raise OAuthApplicationUnavailable()
            if self._valid(application):
                return application
        claim = ClaimedOAuthApplication(registration_id=uuid4().hex, claim_id=uuid4().hex, binding=binding)
        self.applications[claim.registration_id] = claim
        return claim

    async def complete(self, command: CompleteOAuthApplication) -> ReadyOAuthApplication:
        if self.applications.get(command.claim.registration_id) != command.claim:
            raise OAuthApplicationUnavailable()
        ready = ReadyOAuthApplication(registration_id=command.claim.registration_id, binding=command.claim.binding, credentials=command.credentials)
        if not self._valid(ready):
            raise OAuthApplicationUnavailable()
        self.applications[ready.registration_id] = ready
        return ready

    async def resolve(self, query: ResolveOAuthApplication) -> ReadyOAuthApplication:
        ready = self.applications.get(query.reference.registration_id)
        if not isinstance(ready, ReadyOAuthApplication) or ready.binding != query.binding or ready.credentials.client_id != query.client_id or not self._valid(ready):
            raise OAuthApplicationUnavailable()
        return ready
