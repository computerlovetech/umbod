"""MCP SDK OAuth adapter. One encrypted authorization belongs to one connector.

Interactive callbacks are supplied by the hosting product, never by tool calls.
SDK-specific token and issuer metadata stay out of the connector domain model.
"""

import asyncio
import time
from weakref import WeakValueDictionary
from collections.abc import Awaitable, Callable

from mcp.client.auth import AuthorizationCodeResult, OAuthClientProvider
from mcp.shared.auth import (
    OAuthClientInformationFull,
    OAuthClientMetadata,
    OAuthMetadata,
    OAuthToken,
)
from pydantic import BaseModel, Field, SecretStr
import httpx2

from umbod.core.connectors.downstream_mcp.models import OAuthCredentialState
from umbod.core.connectors.downstream_mcp.stores.ports import (
    ConnectorIdQuery,
    CredentialFound,
    EncryptedCredentialStore,
)


class SignInRequired(ValueError):
    def __init__(self) -> None:
        super().__init__("This connection needs browser sign-in. Open Umbod to reconnect it.")


_authorization_locks: WeakValueDictionary = WeakValueDictionary()


class AuthorizationDocument(BaseModel):
    endpoint_url: str
    client_info: OAuthClientInformationFull | None = Field(default=None, repr=False)
    tokens: OAuthToken | None = Field(default=None, repr=False)
    expires_at: float | None = None
    metadata: OAuthMetadata | None = None
    authorization_server: str | None = None


class ConnectorOAuthStorage:
    """SDK TokenStorage with atomic token/expiry writes and stale-write protection."""

    def __init__(
        self,
        document: AuthorizationDocument,
        connector_id: str = "",
        credentials: EncryptedCredentialStore | None = None,
    ) -> None:
        self.document = document
        self.connector_id = connector_id
        self.credentials = credentials
        self._expected: SecretStr | None = None

    async def load(self) -> None:
        if self.credentials is None:
            return
        result = await self.credentials.get(ConnectorIdQuery(connector_id=self.connector_id))
        if isinstance(result, CredentialFound):
            if not isinstance(result.credential, OAuthCredentialState):
                raise SignInRequired()
            document = AuthorizationDocument.model_validate_json(
                result.credential.authorization.get_secret_value()
            )
            if document.endpoint_url != self.document.endpoint_url:
                raise SignInRequired()
            self.document = document
            self._expected = result.credential.authorization
        else:
            raise SignInRequired()

    async def save(self) -> None:
        if self.credentials is not None and self._expected is not None:
            replacement = self.export()
            if not await self.credentials.replace_oauth_authorization(
                self.connector_id, self._expected, replacement
            ):
                raise SignInRequired()
            self._expected = replacement

    def export(self) -> SecretStr:
        return SecretStr(self.document.model_dump_json())

    async def get_tokens(self) -> OAuthToken | None:
        return self.document.tokens

    async def set_tokens(self, tokens: OAuthToken) -> None:
        self.document.tokens = tokens
        self.document.expires_at = (
            time.time() + tokens.expires_in if tokens.expires_in is not None else None
        )
        await self.save()

    async def get_client_info(self) -> OAuthClientInformationFull | None:
        return self.document.client_info

    async def set_client_info(self, client_info: OAuthClientInformationFull) -> None:
        self.document.client_info = client_info
        await self.save()


async def require_sign_in(_url: str) -> None:
    raise SignInRequired()


class ConnectorOAuth(OAuthClientProvider):
    def __init__(
        self,
        storage: ConnectorOAuthStorage,
        redirect_uri: str = "http://127.0.0.1/oauth/callback",
        redirect_handler: Callable[[str], Awaitable[None]] = require_sign_in,
        callback_handler: Callable[[], Awaitable[AuthorizationCodeResult]] | None = None,
    ) -> None:
        self.storage = storage
        super().__init__(
            server_url=storage.document.endpoint_url,
            client_metadata=OAuthClientMetadata(
                client_name="Umbod",
                redirect_uris=[redirect_uri],
                grant_types=["authorization_code", "refresh_token"],
                response_types=["code"],
            ),
            storage=storage,
            redirect_handler=redirect_handler,
            callback_handler=callback_handler,
        )

    async def _initialize(self) -> None:
        await self.storage.load()
        await super()._initialize()
        self.context.token_expiry_time = self.storage.document.expires_at
        self.context.oauth_metadata = self.storage.document.metadata
        self.context.auth_server_url = self.storage.document.authorization_server

    async def _handle_oauth_metadata_response(self, response: httpx2.Response) -> None:
        await super()._handle_oauth_metadata_response(response)
        self.storage.document.metadata = self.context.oauth_metadata
        self.storage.document.authorization_server = self.context.auth_server_url
        await self.storage.save()

    async def _perform_authorization(self) -> httpx2.Request:
        # Fail before registration/browser interaction in background runtime clients.
        if self.context.callback_handler is None:
            raise SignInRequired()
        return await super()._perform_authorization()

    async def async_auth_flow(self, request: httpx2.Request):
        # Local's API and MCP clients share a process, but not provider instances.
        # Serialize token use/rotation and reload the latest encrypted document.
        key = (
            id(asyncio.get_running_loop()),
            self.storage.connector_id or id(self.storage),
            self.storage.document.endpoint_url,
        )
        lock = _authorization_locks.setdefault(key, asyncio.Lock())
        async with lock:
            self._initialized = False
            flow = super().async_auth_flow(request)
            response = None
            try:
                while True:
                    try:
                        outgoing = await flow.asend(response)
                    except StopAsyncIteration:
                        return
                    metadata = self.context.oauth_metadata
                    if (
                        self.context.callback_handler is None
                        and metadata is not None
                        and metadata.registration_endpoint is not None
                        and str(outgoing.url) == str(metadata.registration_endpoint)
                    ):
                        raise SignInRequired()
                    response = yield outgoing
            finally:
                await flow.aclose()
