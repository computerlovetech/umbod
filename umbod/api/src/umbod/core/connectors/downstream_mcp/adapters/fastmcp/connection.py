import ssl
from typing import Protocol, TypeAlias

import httpx2
from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport
from pydantic import SecretStr

from umbod.core.connectors.downstream_mcp.adapters.fastmcp.oauth import (
    AuthorizationDocument,
    ConnectorOAuth,
    ConnectorOAuthStorage,
    SignInRequired,
)
from umbod.core.connectors.downstream_mcp.connection import (
    DownstreamMcpConnectionConfiguration,
    OAuthConnectionConfiguration,
    StaticBearerConnectionConfiguration,
)
from umbod.core.connectors.downstream_mcp.probe import (
    DownstreamConnectorValidationError,
    DownstreamConnectorValidationFailed,
)
from umbod.core.connectors.downstream_mcp.stores.ports import EncryptedCredentialStore

TlsVerification: TypeAlias = ssl.SSLContext | bool | str


class FastMCPConnectionStrategy(Protocol):
    @property
    def configuration(self) -> DownstreamMcpConnectionConfiguration: ...

    def create_client(self) -> Client: ...

    def export_authorization(self, client: Client) -> SecretStr | None: ...


class FastMCPConnectionFactory(Protocol):
    def create(
        self, configuration: DownstreamMcpConnectionConfiguration
    ) -> FastMCPConnectionStrategy: ...


class _FastMCPConnection:
    def __init__(
        self,
        configuration: DownstreamMcpConnectionConfiguration,
        tls_verification: TlsVerification,
    ) -> None:
        self._configuration = configuration
        self._tls_verification = tls_verification

    @property
    def configuration(self) -> DownstreamMcpConnectionConfiguration:
        return self._configuration

    def _create_http_client(self, **kwargs: object) -> httpx2.AsyncClient:
        kwargs["follow_redirects"] = False
        kwargs["verify"] = self._tls_verification
        return httpx2.AsyncClient(**kwargs)

    def _create_transport(
        self,
        *,
        headers: dict[str, str] | None = None,
        auth: ConnectorOAuth | None = None,
    ) -> StreamableHttpTransport:
        transport = StreamableHttpTransport(
            url=self._configuration.endpoint_url,
            headers=headers,
            auth=auth,
            httpx_client_factory=self._create_http_client,
        )
        transport.verify = self._tls_verification
        return transport

    def export_authorization(self, client: Client) -> SecretStr | None:
        return None


class FastMCPUnauthenticatedConnection(_FastMCPConnection):
    def create_client(self) -> Client:
        return Client(self._create_transport(headers={}))


class FastMCPStaticBearerConnection(_FastMCPConnection):
    def __init__(
        self,
        configuration: StaticBearerConnectionConfiguration,
        tls_verification: TlsVerification,
    ) -> None:
        super().__init__(configuration, tls_verification)
        self._bearer_configuration = configuration

    def create_client(self) -> Client:
        configuration = self._bearer_configuration
        token = configuration.bearer_token.get_secret_value()
        if configuration.header_type == "bearer":
            headers = {"Authorization": f"Bearer {token}"}
        elif configuration.header_type == "basic":
            headers = {"Authorization": f"Basic {token}"}
        else:
            if configuration.custom_header_name is None:
                raise ValueError("custom header name is required")
            headers = {configuration.custom_header_name: token}
        return Client(self._create_transport(headers=headers))


class FastMCPOAuthConnection(_FastMCPConnection):
    def __init__(
        self,
        configuration: OAuthConnectionConfiguration,
        tls_verification: TlsVerification,
        credentials: EncryptedCredentialStore | None,
    ) -> None:
        super().__init__(configuration, tls_verification)
        document = AuthorizationDocument.model_validate_json(
            configuration.authorization.get_secret_value()
        )
        if document.endpoint_url != configuration.endpoint_url:
            raise SignInRequired()
        self._oauth = ConnectorOAuth(
            ConnectorOAuthStorage(
                document,
                configuration.connector_id,
                credentials if configuration.persist_refresh else None,
            )
        )

    def create_client(self) -> Client:
        return Client(self._create_transport(auth=self._oauth))

    def export_authorization(self, client: Client) -> SecretStr | None:
        return self._oauth.storage.export()


class FastMCPDownstreamConnectionFactory:
    def __init__(
        self,
        tls_verification: TlsVerification,
        credentials: EncryptedCredentialStore | None = None,
        *,
        oauth_enabled: bool = False,
    ) -> None:
        self._tls_verification = tls_verification
        self._credentials = credentials
        self._oauth_enabled = oauth_enabled

    def create(
        self, configuration: DownstreamMcpConnectionConfiguration
    ) -> FastMCPConnectionStrategy:
        if configuration.connection_type == "none":
            return FastMCPUnauthenticatedConnection(
                configuration, self._tls_verification
            )
        if configuration.connection_type == "static_bearer":
            return FastMCPStaticBearerConnection(
                configuration, self._tls_verification
            )
        if not self._oauth_enabled:
            raise DownstreamConnectorValidationError(
                DownstreamConnectorValidationFailed(code="oauth_disabled")
            )
        return FastMCPOAuthConnection(
            configuration,
            self._tls_verification,
            self._credentials,
        )
