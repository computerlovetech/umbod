from fastmcp.server.auth.auth import TokenVerifier as FastMCPTokenVerifier
from fastmcp.server.auth.providers.auth0 import Auth0Provider
from fastmcp.server.auth.providers.azure import AzureProvider
from fastmcp.server.auth.providers.google import GoogleProvider
from key_value.aio.protocols import AsyncKeyValue

from umbod.mcp.auth.client_storage import MCPOAuthClientStorageFactory
from umbod.mcp.auth.local_test_auth import SingleTestUserOAuthProvider
from umbod.mcp.settings import MCPAppSettings

MCPAuthProvider = (
    FastMCPTokenVerifier
    | Auth0Provider
    | AzureProvider
    | GoogleProvider
    | SingleTestUserOAuthProvider
)


class MCPAuthProviderFactory:
    def create(self, settings: MCPAppSettings) -> MCPAuthProvider | None:
        auth_mode = settings.mcp.auth_mode
        if auth_mode == "none":
            return None
        if auth_mode == "single_test_user":
            return SingleTestUserOAuthProvider(
                bearer_token=settings.mcp.test_bearer_token,
                base_url=settings.endpoints.mcp_base_url,
            )
        if auth_mode == "oidc":
            return self._create_oidc_provider(settings)
        raise ValueError(f"Unsupported UMBOD_MCP_AUTH_MODE: {auth_mode}")

    def _create_oidc_provider(self, settings: MCPAppSettings) -> MCPAuthProvider:
        provider = settings.oidc.provider
        client_storage = MCPOAuthClientStorageFactory().create(settings.oauth_storage)
        if provider == "google":
            return self._create_google_provider(settings, client_storage)
        if provider == "azure_entra_id":
            return self._create_azure_provider(settings, client_storage)
        if provider == "auth0":
            return self._create_auth0_provider(settings, client_storage)
        raise ValueError(f"Unsupported UMBOD_OIDC_PROVIDER: {provider}")

    def _create_google_provider(
        self, settings: MCPAppSettings, client_storage: AsyncKeyValue
    ) -> GoogleProvider:
        return GoogleProvider(
            client_id=settings.oidc.client_id,
            client_secret=settings.oidc.client_secret or None,
            base_url=settings.endpoints.mcp_base_url,
            issuer_url=settings.oidc.issuer_url or None,
            required_scopes=settings.oidc.required_scopes,
            client_storage=client_storage,
            jwt_signing_key=settings.oidc.jwt_signing_key or None,
        )

    def _create_azure_provider(
        self, settings: MCPAppSettings, client_storage: AsyncKeyValue
    ) -> AzureProvider:
        return AzureProvider(
            client_id=settings.oidc.client_id,
            client_secret=settings.oidc.client_secret or None,
            tenant_id=settings.oidc.tenant_id,
            required_scopes=settings.oidc.required_scopes,
            base_url=settings.endpoints.mcp_base_url,
            issuer_url=settings.oidc.issuer_url or None,
            client_storage=client_storage,
            jwt_signing_key=settings.oidc.jwt_signing_key or None,
        )

    def _create_auth0_provider(
        self, settings: MCPAppSettings, client_storage: AsyncKeyValue
    ) -> Auth0Provider:
        return Auth0Provider(
            config_url=settings.oidc.config_url,
            client_id=settings.oidc.client_id,
            client_secret=settings.oidc.client_secret,
            audience=settings.oidc.audience,
            base_url=settings.endpoints.mcp_base_url,
            issuer_url=settings.oidc.issuer_url or None,
            required_scopes=settings.oidc.required_scopes,
            client_storage=client_storage,
            jwt_signing_key=settings.oidc.jwt_signing_key or None,
        )
