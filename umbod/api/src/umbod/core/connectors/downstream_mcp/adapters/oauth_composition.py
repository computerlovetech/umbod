import httpx2

from umbod.core.connectors.downstream_mcp.adapters.fastmcp.oauth_client import (
    oauth_client,
)
from umbod.core.connectors.downstream_mcp.adapters.fastmcp.oauth_session import (
    FastMCPOAuthSessionFactory,
)
from umbod.core.connectors.downstream_mcp.adapters.oauth_discovery import (
    HttpOAuthDiscovery,
)
from umbod.core.connectors.downstream_mcp.oauth.ports import OAuthHost
from umbod.core.connectors.downstream_mcp.oauth.service import OAuthService


def create_metadata_client() -> httpx2.AsyncClient:
    return httpx2.AsyncClient(timeout=8, follow_redirects=False)


def create_oauth_service(host: OAuthHost) -> OAuthService:
    return OAuthService(
        host,
        FastMCPOAuthSessionFactory(oauth_client),
        HttpOAuthDiscovery(create_metadata_client),
    )
