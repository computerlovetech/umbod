"""FastMCP session adapter used by shared OAuth orchestration."""
from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport
from httpx2 import Auth


def oauth_client(endpoint_url: str, auth: Auth) -> Client:
    return Client(StreamableHttpTransport(endpoint_url, auth=auth))
