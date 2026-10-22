import re
from datetime import timedelta
from typing import Literal
from urllib.parse import urlencode

import anyio
from pydantic import BaseModel, ConfigDict, SecretStr

from ...personal_connections.authorization_models import (
    ExpiringPersonalToken,
    PersonalOAuthGrant,
    PresentPersonalRefreshToken,
    authorize_personal_grant,
)
from ...personal_connections.models import Authorized
from ...personal_connections.refresh_provider_models import (
    PersonalOAuthRefreshDenied,
    PersonalOAuthRefreshUncertain,
    RefreshPersonalOAuth,
)
from ...personal_oauth_configuration.models import parse_oauth_scopes
from .refresh_logging import private_refresh_network_logs
from .callback import CallbackURLPolicy, validate_callback_url
from .transport import (
    BasicOAuthHttpAuthentication,
    NoOAuthHttpAuthentication,
    OAuthHttpAuthentication,
    OAuthHttpRequest,
    OAuthHttpTransport,
)
from .validation import TokenResponse, parse_json, validated_url


class _TokenEndpointError(BaseModel):
    model_config = ConfigDict(strict=True)

    error: Literal["invalid_grant", "invalid_client"]
    error_description: str = ""
    error_uri: str = ""


def _definitive_denial(status: int, raw: dict[str, object]) -> bool:
    if status not in (400, 401) or any(key in raw for key in ("access_token", "refresh_token", "token_type", "expires_in", "scope")):
        return False
    error = _TokenEndpointError.model_validate(raw)
    return all(
        re.fullmatch(r"[\x20-\x21\x23-\x5b\x5d-\x7e]*", value)
        for value in (error.error_description, error.error_uri)
    )


class StoredPersonalOAuthRefreshProvider:
    def __init__(self, callback_policy: CallbackURLPolicy, transport: OAuthHttpTransport) -> None:
        self._callback_policy = callback_policy
        self._transport = transport

    async def refresh(self, command: RefreshPersonalOAuth) -> Authorized:
        outcome: Authorized | Literal["denied", "uncertain"] = "uncertain"
        try:
            with private_refresh_network_logs(), anyio.fail_after(command.timeout_seconds):
                outcome = await self._refresh(command)
        except Exception:
            pass
        if isinstance(outcome, Authorized):
            return outcome
        if outcome == "denied":
            raise PersonalOAuthRefreshDenied("Personal OAuth refresh denied")
        raise PersonalOAuthRefreshUncertain("Personal OAuth refresh outcome uncertain")

    async def _refresh(self, command: RefreshPersonalOAuth) -> Authorized | Literal["denied"]:
        grant = PersonalOAuthGrant.model_validate(command.grant.model_dump())
        policy = command.policy
        client = policy.client
        method = client.token_endpoint_auth_method if client.kind == "preconfigured_confidential" else "none"
        if (
            client.kind == "dynamic_public"
            or grant.client_mode != client.kind
            or grant.token_endpoint_auth_method != method
            or grant.configuration_revision != policy.revision
            or grant.requested_scopes != policy.requested_scopes
            or not isinstance(grant.refresh_token, PresentPersonalRefreshToken)
            or not isinstance(grant.lifetime, ExpiringPersonalToken)
            or grant.issued_at > command.now
        ):
            raise ValueError("Unsupported refresh binding")
        if grant.client_id != client.client_id or grant.issuer != client.issuer_url:
            raise ValueError("Unsupported refresh binding")
        validate_callback_url(grant.redirect_uri, self._callback_policy)
        for url in (grant.issuer, grant.resource, grant.token_endpoint):
            validated_url(url)
        parameters = {
            "grant_type": "refresh_token",
            "refresh_token": grant.refresh_token.token.get_secret_value(),
            "resource": grant.resource,
        }
        authentication: OAuthHttpAuthentication = NoOAuthHttpAuthentication()
        if client.kind == "preconfigured_confidential" and method == "client_secret_basic":
            authentication = BasicOAuthHttpAuthentication(client_id=SecretStr(client.client_id), client_secret=client.client_secret)
        else:
            parameters["client_id"] = grant.client_id
            if client.kind == "preconfigured_confidential":
                parameters["client_secret"] = client.client_secret.get_secret_value()
        response = await self._transport.request(OAuthHttpRequest(
            method="POST", url=grant.token_endpoint, body=SecretStr(urlencode(parameters)),
            content_type="application/x-www-form-urlencoded", authentication=authentication,
        ))
        raw = parse_json(response.body)
        if not 200 <= response.status < 300:
            if _definitive_denial(response.status, raw):
                return "denied"
            raise ValueError("Uncertain token endpoint response")
        token = TokenResponse.model_validate(raw)
        if "error" in raw or token.token_type.lower() != "bearer" or token.expires_in <= 0:
            raise ValueError("Unsupported refresh response")
        scopes = parse_oauth_scopes(token.scope) if "scope" in raw else grant.granted_scopes
        if not set(scopes).issubset(grant.granted_scopes):
            raise ValueError("Expanded refresh scopes")
        expiry = command.now + timedelta(seconds=token.expires_in)
        if expiry <= command.now:
            raise ValueError("Unsupported refresh expiry")
        refresh_token = PresentPersonalRefreshToken(token=token.refresh_token) if "refresh_token" in raw else grant.refresh_token
        renewed = PersonalOAuthGrant.model_validate({
            **grant.model_dump(),
            "issued_at": command.now,
            "lifetime": ExpiringPersonalToken(expires_at=expiry),
            "access_token": token.access_token,
            "refresh_token": refresh_token,
            "granted_scopes": scopes,
        })
        return authorize_personal_grant(renewed)
