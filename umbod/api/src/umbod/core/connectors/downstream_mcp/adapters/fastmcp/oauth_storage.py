from typing import Protocol

from mcp.shared.auth import OAuthClientInformationFull, OAuthMetadata, OAuthToken
from pydantic import BaseModel, Field, SecretStr


class AuthorizationDocument(BaseModel):
    endpoint_url: str
    client_info: OAuthClientInformationFull | None = Field(default=None, repr=False)
    tokens: OAuthToken | None = Field(default=None, repr=False)
    expires_at: float | None = None
    metadata: OAuthMetadata | None = None
    authorization_server: str | None = None


class ConnectorOAuthStorage(Protocol):
    document: AuthorizationDocument
    connector_id: str

    async def load(self) -> None: ...
    async def save(self) -> None: ...
    def export(self) -> SecretStr: ...
    async def get_tokens(self) -> OAuthToken | None: ...
    async def set_tokens(self, tokens: OAuthToken) -> None: ...
    async def get_client_info(self) -> OAuthClientInformationFull | None: ...
    async def set_client_info(self, client_info: OAuthClientInformationFull) -> None: ...
