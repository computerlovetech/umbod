import json
import socket
from datetime import datetime, timezone
from dataclasses import dataclass

import anyio
import pytest
from pydantic import SecretStr

from umbod.core.connectors.downstream_mcp.personal_connections.oauth_callback_models import GenericRoute, IssuerBinding, IssuerRoute, PresentCallbackIssuer

from umbod.core.connectors.downstream_mcp.adapters.personal_oauth.transport import OAuthHttpResponse
from umbod.core.connectors.downstream_mcp.personal_connections.models import (
    CanonicalPrincipal,
    PersonalConnectionKey,
)
from umbod.core.connectors.downstream_mcp.personal_connections.oauth_models import (
    ClaimedPersonalOAuthAttempt,
    ExchangePersonalOAuth,
    PersonalOAuthAttemptQuery,
    PreparePersonalOAuth,
    PreparedPersonalOAuth,
)


@pytest.fixture
def public_dns(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    queries: list[str] = []

    async def resolve(host: str, port: int, *, type: int) -> list[tuple[int, int, int, str, tuple[str, int]]]:
        queries.append(host)
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port))]

    monkeypatch.setattr(anyio, "getaddrinfo", resolve)
    return queries


def response(value: dict[str, object]) -> OAuthHttpResponse:
    return OAuthHttpResponse(status=200, body=json.dumps(value).encode())


@pytest.fixture
def preparation() -> PreparePersonalOAuth:
    return PreparePersonalOAuth(
        endpoint_url="https://resource.example/mcp",
        redirect_uri="https://umbod.example/api/oauth/downstream-mcp/callback",
        state=SecretStr("opaque-state"), code_verifier=SecretStr("a" * 43),
    )


@pytest.fixture
def resource_metadata() -> dict[str, object]:
    return {"resource": "https://resource.example/mcp", "authorization_servers": ["https://issuer.example/tenant"]}


@pytest.fixture
def server_metadata() -> dict[str, object]:
    return {
        "issuer": "https://issuer.example/tenant",
        "authorization_endpoint": "https://issuer.example/authorize",
        "token_endpoint": "https://issuer.example/token",
        "registration_endpoint": "https://issuer.example/register",
        "code_challenge_methods_supported": ["S256"],
        "grant_types_supported": ["authorization_code"],
        "response_types_supported": ["code"],
        "token_endpoint_auth_methods_supported": ["none"],
        "authorization_response_iss_parameter_supported": True,
    }


@pytest.fixture
def client_metadata(preparation: PreparePersonalOAuth) -> dict[str, object]:
    return {
        "client_id": "public-client", "redirect_uris": [preparation.redirect_uri],
        "token_endpoint_auth_method": "none", "grant_types": ["authorization_code"],
        "response_types": ["code"],
    }


@dataclass(frozen=True)
class ProviderCase:
    preparation: PreparePersonalOAuth
    resource_metadata: dict[str, object]
    server_metadata: dict[str, object]
    client_metadata: dict[str, object]


@pytest.fixture
def provider_case(
    preparation: PreparePersonalOAuth, resource_metadata: dict[str, object],
    server_metadata: dict[str, object], client_metadata: dict[str, object],
) -> ProviderCase:
    return ProviderCase(preparation, resource_metadata, server_metadata, client_metadata)


def exchange_command(preparation: PreparePersonalOAuth, prepared: PreparedPersonalOAuth) -> ExchangePersonalOAuth:
    return ExchangePersonalOAuth(
        route=IssuerRoute(kind="issuer", issuer_key=prepared.callback_binding.issuer_key)
        if isinstance(prepared.callback_binding, IssuerBinding) else GenericRoute(kind="generic"),
        attempt=ClaimedPersonalOAuthAttempt(
            query=PersonalOAuthAttemptQuery(
                key=PersonalConnectionKey(
                    principal=CanonicalPrincipal(namespace="issuer", subject="owner"), connector_id="connector",
                ), attempt_id="attempt", now=datetime.now(timezone.utc),
            ), claim_id="claim", preparation=preparation, prepared=prepared,
        ), code=SecretStr("authorization-code"), issuer=PresentCallbackIssuer(kind="present", value="https://issuer.example/tenant"),
    )
