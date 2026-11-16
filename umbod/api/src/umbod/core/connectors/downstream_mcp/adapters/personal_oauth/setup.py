from collections.abc import Awaitable, Callable
from typing import TypeVar

import anyio
from pydantic import TypeAdapter

from umbod.core.invocation.diagnostics import DownstreamHttpResponse, NoDownstreamResponse
from ...personal_connections.oauth_failure_models import OAuthFailureEvidence
from ...personal_connections.oauth_models import PersonalOAuthProviderFailure, PersonalOAuthProviderUnsupported
from ...personal_oauth_configuration.models import OAuthScopes, parse_oauth_scopes
from ...personal_oauth_setup.models import (
    DiscoverPersonalOAuthSetup,
    PersonalOAuthSetupDiscovery,
    PersonalOAuthSetupScopeMismatch,
    PersonalOAuthSetupValidation,
    ValidatePersonalOAuthSetup,
    ValidatedPersonalOAuthSetup,
)
from .failure import OAuthOperationProgress, oauth_failure_boundary
from .provider import DiscoveredPersonalOAuthProvider, unsupported_configuration
from .transport import OAuthDestination
from .validation import DiscoveredOAuthServer, validated_url


SetupResult = TypeVar("SetupResult")
_SCOPE_ADAPTER = TypeAdapter(OAuthScopes)


async def bounded_setup_operation(operation: Callable[[OAuthOperationProgress], Awaitable[SetupResult]]) -> SetupResult:
    progress = OAuthOperationProgress(stage="discovery")
    try:
        with anyio.fail_after(60):
            return await operation(progress)
    except (PersonalOAuthProviderFailure, PersonalOAuthProviderUnsupported):
        raise
    except ValueError:
        raise PersonalOAuthProviderUnsupported(OAuthFailureEvidence(
            stage=progress.stage, reason="invalid_response", downstream_response=NoDownstreamResponse(),
        )) from None
    except Exception as error:
        raise PersonalOAuthProviderFailure(progress.failure_evidence(error)) from None


def discovery_projection(discovered: DiscoveredOAuthServer, command: DiscoverPersonalOAuthSetup) -> PersonalOAuthSetupDiscovery:
    resource_scopes = _SCOPE_ADAPTER.validate_python(tuple(discovered.resource.scopes_supported))
    server_scopes = _SCOPE_ADAPTER.validate_python(tuple(discovered.server.scopes_supported))
    scopes = _SCOPE_ADAPTER.validate_python(tuple(sorted(set(resource_scopes + server_scopes))))
    return PersonalOAuthSetupDiscovery(
        issuer_url=discovered.server.issuer,
        redirect_uri=discovered.redirect_uri,
        available_scopes=scopes,
        registration_mode=command.policy.client.kind,
    )


class DiscoveredPersonalOAuthSetupProvider(DiscoveredPersonalOAuthProvider):
    async def discover(self, command: DiscoverPersonalOAuthSetup) -> PersonalOAuthSetupDiscovery:
        async def operation(progress: OAuthOperationProgress) -> PersonalOAuthSetupDiscovery:
            discovered = await self._discover_setup(command, progress, True)
            return discovery_projection(discovered, command)

        return await bounded_setup_operation(operation)

    async def validate(self, command: ValidatePersonalOAuthSetup) -> PersonalOAuthSetupValidation:
        async def operation(progress: OAuthOperationProgress) -> PersonalOAuthSetupValidation:
            discovered = await self._discover_setup(command, progress, False)
            discovery = discovery_projection(discovered, command)
            if command.policy.client.kind != "dynamic_public":
                return ValidatedPersonalOAuthSetup(discovery=discovery, returned_scopes=(), scope_source="not_checked")
            progress.begin("registration")
            registered = await self._register(discovered.redirect_uri, command.policy, discovered.server, progress)
            with oauth_failure_boundary("registration", DownstreamHttpResponse(status_code=registered.status_code)):
                returned_scopes = (
                    parse_oauth_scopes(registered.client.scope)
                    if "scope" in registered.client.model_fields_set else ()
                )
            if "scope" in registered.client.model_fields_set and returned_scopes != command.policy.requested_scopes:
                return PersonalOAuthSetupScopeMismatch(
                    discovery=discovery, returned_scopes=returned_scopes,
                    downstream_response=DownstreamHttpResponse(status_code=registered.status_code),
                )
            return ValidatedPersonalOAuthSetup(
                discovery=discovery, returned_scopes=returned_scopes,
                scope_source="registration" if "scope" in registered.client.model_fields_set else "not_returned",
            )

        return await bounded_setup_operation(operation)

    async def _discover_setup(
        self, command: DiscoverPersonalOAuthSetup, progress: OAuthOperationProgress, select_advertised_issuer: bool,
    ) -> DiscoveredOAuthServer:
        discovered = await self._discover(command.endpoint_url, command.redirect_uri, command.policy, progress, select_advertised_issuer)
        with oauth_failure_boundary("discovery", NoDownstreamResponse()):
            await self._transport.validate_destination(OAuthDestination(url=discovered.server.token_endpoint))
            if command.policy.client.kind == "dynamic_public":
                if not discovered.server.registration_endpoint:
                    raise unsupported_configuration("registration_unavailable", "discovery")
                validated_url(discovered.server.registration_endpoint)
                await self._transport.validate_destination(OAuthDestination(url=discovered.server.registration_endpoint))
        return discovered
