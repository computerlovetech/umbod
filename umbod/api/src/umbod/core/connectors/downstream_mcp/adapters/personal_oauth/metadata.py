from ...personal.oauth.configuration import DynamicConfidentialOAuthClient, DynamicPublicOAuthClient
from ...personal.oauth.metadata import (
    DiscoverPersonalOAuthMetadata,
    DiscoveredPersonalOAuthMetadata,
    PersonalOAuthIssuerSelectionRequired,
    PersonalOAuthMetadataResult,
    UnavailableAutomaticOAuthClient,
)
from .discovery import authorization_server_metadata, protected_resource_metadata, unsupported_metadata
from .failure import OAuthOperationProgress, oauth_failure_boundary
from .setup import bounded_setup_operation
from .transport import OAuthDestination, OAuthHttpTransport
from .validation import validated_url
from umbod.core.invocation.diagnostics import DownstreamHttpResponse


class DiscoveredPersonalOAuthMetadataProvider:
    def __init__(self, transport: OAuthHttpTransport) -> None:
        self._transport = transport

    async def discover(self, command: DiscoverPersonalOAuthMetadata) -> PersonalOAuthMetadataResult:
        async def operation(progress: OAuthOperationProgress) -> PersonalOAuthMetadataResult:
            resource = await protected_resource_metadata(command.endpoint_url, self._transport, progress)
            issuers = resource.authorization_servers
            selection = command.issuer_selection
            if selection.kind == "selected":
                issuer = selection.issuer_url
                if issuer not in issuers:
                    raise unsupported_metadata("issuer_mismatch")
            elif len(issuers) > 1:
                return PersonalOAuthIssuerSelectionRequired(endpoint_url=command.endpoint_url, issuer_urls=tuple(issuers))
            else:
                issuer = issuers[0]
            server, metadata_status = await authorization_server_metadata(issuer, self._transport, progress)
            with oauth_failure_boundary("discovery", DownstreamHttpResponse(status_code=metadata_status)):
                await self._transport.validate_destination(OAuthDestination(url=server.token_endpoint))
                automatic_client: DynamicPublicOAuthClient | DynamicConfidentialOAuthClient | UnavailableAutomaticOAuthClient = UnavailableAutomaticOAuthClient()
                methods = server.token_endpoint_auth_methods_supported
                if server.registration_endpoint:
                    if "none" in methods:
                        automatic_client = DynamicPublicOAuthClient(approved_issuers=(issuer,))
                    elif "client_secret_basic" in methods:
                        automatic_client = DynamicConfidentialOAuthClient(approved_issuers=(issuer,), token_endpoint_auth_method="client_secret_basic")
                    elif "client_secret_post" in methods:
                        automatic_client = DynamicConfidentialOAuthClient(approved_issuers=(issuer,), token_endpoint_auth_method="client_secret_post")
                registration_available = automatic_client.kind != "unavailable"
                if server.registration_endpoint:
                    validated_url(server.registration_endpoint)
                    await self._transport.validate_destination(OAuthDestination(url=server.registration_endpoint))
                scope_source = "unavailable"
                scopes: tuple[str, ...] = ()
                if "scopes_supported" in resource.model_fields_set:
                    scopes = tuple(resource.scopes_supported)
                    scope_source = "resource"
                elif "scopes_supported" in server.model_fields_set:
                    scopes = tuple(server.scopes_supported)
                    scope_source = "authorization_server"
                return DiscoveredPersonalOAuthMetadata(
                    endpoint_url=command.endpoint_url, issuer_url=issuer,
                    available_scopes=scopes, scope_source=scope_source,
                    automatic_registration="available" if registration_available else "unavailable",
                    automatic_client=automatic_client,
                    token_endpoint_auth_methods=tuple(server.token_endpoint_auth_methods_supported),
                )

        return await bounded_setup_operation(operation)
