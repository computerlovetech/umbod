import time
from abc import ABC, abstractmethod

from mcp.shared.auth import OAuthClientInformationFull, OAuthToken
from pydantic import SecretStr

from umbod.core.connectors.downstream_mcp.adapters.fastmcp.oauth import SignInRequired
from umbod.core.connectors.downstream_mcp.adapters.fastmcp.oauth_storage import AuthorizationDocument
from umbod.core.connectors.downstream_mcp.models import OAuthCredentialState
from umbod.core.connectors.downstream_mcp.stores.ports import (
    ConnectorIdQuery,
    CredentialFound,
    EncryptedCredentialStore,
)


class _DocumentOAuthStorage(ABC):
    def __init__(self, document: AuthorizationDocument, connector_id: str) -> None:
        self.document = document
        self.connector_id = connector_id

    @abstractmethod
    async def load(self) -> None: ...

    @abstractmethod
    async def save(self) -> None: ...

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


class DetachedConnectorOAuthStorage(_DocumentOAuthStorage):
    async def load(self) -> None:
        return None

    async def save(self) -> None:
        return None


class PersistedConnectorOAuthStorage(_DocumentOAuthStorage):
    def __init__(
        self,
        document: AuthorizationDocument,
        connector_id: str,
        credentials: EncryptedCredentialStore,
    ) -> None:
        super().__init__(document, connector_id)
        self._credentials = credentials
        self._expected: SecretStr | None = None

    async def load(self) -> None:
        self._expected = None
        result = await self._credentials.get(ConnectorIdQuery(connector_id=self.connector_id))
        if not isinstance(result, CredentialFound):
            raise SignInRequired()
        if not isinstance(result.credential, OAuthCredentialState):
            raise SignInRequired()
        document = AuthorizationDocument.model_validate_json(
            result.credential.authorization.get_secret_value()
        )
        if document.endpoint_url != self.document.endpoint_url:
            raise SignInRequired()
        self.document = document
        self._expected = result.credential.authorization

    async def save(self) -> None:
        if self._expected is None:
            return
        replacement = self.export()
        if not await self._credentials.replace_oauth_authorization(
            self.connector_id, self._expected, replacement
        ):
            raise SignInRequired()
        self._expected = replacement
