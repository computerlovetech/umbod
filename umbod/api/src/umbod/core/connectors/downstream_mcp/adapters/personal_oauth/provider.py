import base64
import hashlib
import json
import re
from datetime import timedelta
from typing import Literal
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import anyio
from pydantic import SecretStr

from ...personal_connections.authorization_models import (
    AbsentPersonalRefreshToken,
    ExpiringPersonalToken,
    PersonalOAuthGrant,
    PresentPersonalRefreshToken,
    UnknownPersonalTokenLifetime,
    authorize_personal_grant,
)
from ...personal_connections.models import Authorized
from ...personal_connections.oauth_models import (
    ExchangePersonalOAuth,
    PersonalOAuthProviderFailure,
    PersonalOAuthProviderUnsupported,
    PreparePersonalOAuth,
    PreparedPersonalOAuth,
)
from ...personal_oauth_configuration.models import (
    PersonalOAuthClient,
    parse_oauth_scopes,
)
from .transport import (
    BasicOAuthHttpAuthentication,
    NoOAuthHttpAuthentication,
    OAuthDestination,
    OAuthHttpAuthentication,
    OAuthHttpRequest,
    OAuthHttpTransport,
)
from .validation import (
    AuthorizationServer,
    ProtectedResource,
    ProviderContext,
    RegisteredClient,
    TokenResponse,
    parse_json,
    validated_url,
)


def verifier_digest(verifier: SecretStr) -> str:
    value = verifier.get_secret_value()
    if not re.fullmatch(r"[A-Za-z0-9._~-]{43,128}", value):
        raise ValueError("Invalid verifier")
    return base64.urlsafe_b64encode(hashlib.sha256(value.encode("ascii")).digest()).rstrip(b"=").decode("ascii")


def client_authentication_method(client: PersonalOAuthClient) -> Literal["none", "client_secret_basic", "client_secret_post"]:
    if client.kind == "preconfigured_confidential":
        return client.token_endpoint_auth_method
    return "none"


class DiscoveredPersonalOAuthProvider:
    def __init__(self, transport: OAuthHttpTransport) -> None:
        self._transport = transport

    async def _request(
        self, method: Literal["GET", "POST"], url: str, body: str,
        content_type: str, authentication: OAuthHttpAuthentication,
    ) -> dict[str, object]:
        validated_url(url)
        response = await self._transport.request(OAuthHttpRequest(
            method=method, url=url, body=SecretStr(body), content_type=content_type,
            authentication=authentication,
        ))
        if response.status not in (200, 201):
            raise PersonalOAuthProviderFailure("Personal OAuth provider request failed")
        return parse_json(response.body)

    async def prepare(self, command: PreparePersonalOAuth) -> PreparedPersonalOAuth:
        try:
            with anyio.fail_after(60):
                return await self._prepare(command)
        except PersonalOAuthProviderFailure:
            raise PersonalOAuthProviderFailure("Personal OAuth provider request failed") from None
        except (ValueError, TypeError, KeyError):
            raise PersonalOAuthProviderUnsupported("Personal OAuth provider is unsupported") from None
        except Exception:
            raise PersonalOAuthProviderFailure("Personal OAuth provider request failed") from None

    async def _prepare(self, command: PreparePersonalOAuth) -> PreparedPersonalOAuth:
        endpoint = validated_url(command.endpoint_url)
        validated_url(command.redirect_uri)
        challenge = verifier_digest(command.code_verifier)
        state_secret = command.state
        state = state_secret.get_secret_value()
        if not state:
            raise ValueError("Invalid state")
        metadata_url = urlunsplit((endpoint.scheme, endpoint.netloc, "/.well-known/oauth-protected-resource" + endpoint.path.rstrip("/"), "", ""))
        response = await self._transport.request(OAuthHttpRequest(
            method="GET", url=metadata_url, content_type="", body=SecretStr(""),
        ))
        if response.status == 404 and endpoint.path.rstrip("/"):
            metadata_url = urlunsplit((endpoint.scheme, endpoint.netloc, "/.well-known/oauth-protected-resource", "", ""))
            response = await self._transport.request(OAuthHttpRequest(
                method="GET", url=metadata_url, content_type="", body=SecretStr(""),
            ))
        if response.status == 429 or 500 <= response.status < 600:
            raise PersonalOAuthProviderFailure("Personal OAuth provider request failed")
        if response.status != 200:
            raise ValueError("Unsupported resource metadata")
        resource = ProtectedResource.model_validate(parse_json(response.body))
        if resource.resource != command.endpoint_url:
            raise ValueError("Resource mismatch")
        policy = command.policy
        configured_client = policy.client
        auth_method = client_authentication_method(configured_client)
        issuer = resource.authorization_servers[0]
        if configured_client.kind != "dynamic_public":
            issuer = configured_client.issuer_url
            if issuer not in resource.authorization_servers:
                raise ValueError("Configured issuer is not advertised")
        issuer_parts = validated_url(issuer)
        issuer_url = urlunsplit((issuer_parts.scheme, issuer_parts.netloc, "/.well-known/oauth-authorization-server" + issuer_parts.path.rstrip("/"), "", ""))
        server = AuthorizationServer.model_validate(await self._request("GET", issuer_url, "", "", NoOAuthHttpAuthentication()))
        if (
            server.issuer != issuer
            or "S256" not in server.code_challenge_methods_supported
            or "authorization_code" not in server.grant_types_supported
            or "code" not in server.response_types_supported
            or auth_method not in server.token_endpoint_auth_methods_supported
            or not server.authorization_response_iss_parameter_supported
        ):
            raise ValueError("Unsupported authorization server")
        for url in (server.authorization_endpoint, server.token_endpoint):
            validated_url(url)
        await self._transport.validate_destination(OAuthDestination(url=server.authorization_endpoint))
        if configured_client.kind == "dynamic_public":
            client_id = await self._register(command, server)
        else:
            client_id = configured_client.client_id
        authorization_parameters = {
            "response_type": "code", "client_id": client_id,
            "redirect_uri": command.redirect_uri, "state": state,
            "code_challenge": challenge, "code_challenge_method": "S256", "resource": command.endpoint_url,
        }
        if policy.requested_scopes:
            authorization_parameters["scope"] = " ".join(policy.requested_scopes)
        authorization_url = server.authorization_endpoint + "?" + urlencode(authorization_parameters)
        context = ProviderContext(
            issuer=issuer, resource=command.endpoint_url, token_endpoint=server.token_endpoint,
            client_id=client_id, redirect_uri=command.redirect_uri,
            authorization_url=authorization_url, verifier_digest=challenge,
            state_digest=hashlib.sha256(state.encode()).hexdigest(),
            policy_revision=policy.revision, requested_scopes=list(policy.requested_scopes),
            client_mode=configured_client.kind, token_endpoint_auth_method=auth_method,
        )
        return PreparedPersonalOAuth(authorization_url=SecretStr(authorization_url), context=SecretStr(context.model_dump_json()))

    async def _register(self, command: PreparePersonalOAuth, server: AuthorizationServer) -> str:
        validated_url(server.registration_endpoint)
        registration: dict[str, object] = {
            "redirect_uris": [command.redirect_uri],
            "token_endpoint_auth_method": "none",
            "grant_types": ["authorization_code"],
            "response_types": ["code"],
        }
        if command.policy.requested_scopes:
            registration["scope"] = " ".join(command.policy.requested_scopes)
        raw_client = await self._request(
            "POST", server.registration_endpoint, json.dumps(registration),
            "application/json", NoOAuthHttpAuthentication(),
        )
        client = RegisteredClient.model_validate(raw_client)
        if (
            "client_secret" in raw_client
            or client.token_endpoint_auth_method != "none"
            or client.redirect_uris != [command.redirect_uri]
            or client.grant_types != ["authorization_code"]
            or client.response_types != ["code"]
            or ("scope" in raw_client and parse_oauth_scopes(client.scope) != command.policy.requested_scopes)
        ):
            raise ValueError("Unsupported registration")
        return client.client_id

    async def exchange(self, command: ExchangePersonalOAuth) -> Authorized:
        try:
            with anyio.fail_after(20):
                return await self._exchange(command)
        except Exception:
            raise PersonalOAuthProviderFailure("Personal OAuth provider request failed") from None

    async def _exchange(self, command: ExchangePersonalOAuth) -> Authorized:
        attempt = command.attempt
        context = ProviderContext.model_validate(parse_json(attempt.prepared.context.get_secret_value().encode()))
        state_secret = attempt.preparation.state
        policy = attempt.preparation.policy
        client = policy.client
        if (
            context.policy_revision != policy.revision
            or tuple(context.requested_scopes) != policy.requested_scopes
            or context.client_mode != client.kind
            or context.token_endpoint_auth_method != client_authentication_method(client)
            or (client.kind != "dynamic_public" and (client.client_id != context.client_id or client.issuer_url != context.issuer))
        ):
            raise ValueError("Invalid policy binding")
        if (
            command.issuer != context.issuer
            or attempt.preparation.endpoint_url != context.resource
            or attempt.preparation.redirect_uri != context.redirect_uri
            or attempt.prepared.authorization_url.get_secret_value() != context.authorization_url
            or verifier_digest(attempt.preparation.code_verifier) != context.verifier_digest
            or hashlib.sha256(state_secret.get_secret_value().encode()).hexdigest() != context.state_digest
            or not command.code.get_secret_value()
        ):
            raise ValueError("Invalid exchange binding")
        authorization_parameters = dict(
            response_type="code", client_id=context.client_id, redirect_uri=context.redirect_uri,
            state=state_secret.get_secret_value(), code_challenge=context.verifier_digest,
            code_challenge_method="S256", resource=context.resource,
        )
        if policy.requested_scopes:
            authorization_parameters["scope"] = " ".join(policy.requested_scopes)
        captured_parameters = parse_qsl(urlsplit(context.authorization_url).query, keep_blank_values=True, strict_parsing=True)
        if len(captured_parameters) != len(authorization_parameters) or dict(captured_parameters) != authorization_parameters:
            raise ValueError("Invalid authorization parameter binding")
        for url in (context.issuer, context.resource, context.redirect_uri, context.token_endpoint):
            validated_url(url)
        token_parameters = {
            "grant_type": "authorization_code", "code": command.code.get_secret_value(),
            "redirect_uri": context.redirect_uri,
            "code_verifier": attempt.preparation.code_verifier.get_secret_value(), "resource": context.resource,
        }
        authentication: OAuthHttpAuthentication = NoOAuthHttpAuthentication()
        if client.kind == "preconfigured_confidential" and client.token_endpoint_auth_method == "client_secret_basic":
            authentication = BasicOAuthHttpAuthentication(client_id=SecretStr(client.client_id), client_secret=client.client_secret)
        else:
            token_parameters["client_id"] = context.client_id
            if client.kind == "preconfigured_confidential":
                token_parameters["client_secret"] = client.client_secret.get_secret_value()
        raw_token = await self._request(
            "POST", context.token_endpoint, urlencode(token_parameters),
            "application/x-www-form-urlencoded", authentication,
        )
        token = TokenResponse.model_validate(raw_token)
        granted_scopes = parse_oauth_scopes(token.scope) if "scope" in raw_token else policy.requested_scopes
        if (
            not set(granted_scopes).issubset(policy.requested_scopes)
            or token.token_type.lower() != "bearer" or "error" in raw_token
            or not re.fullmatch(r"[A-Za-z0-9._~+/-]+=*", token.access_token.get_secret_value())
        ):
            raise ValueError("Unsupported token")
        lifetime = (
            ExpiringPersonalToken(expires_at=attempt.query.now + timedelta(seconds=token.expires_in))
            if "expires_in" in raw_token else UnknownPersonalTokenLifetime()
        )
        refresh_token = (
            PresentPersonalRefreshToken(token=token.refresh_token)
            if "refresh_token" in raw_token else AbsentPersonalRefreshToken()
        )
        return authorize_personal_grant(PersonalOAuthGrant(
            version=2, key=attempt.query.key, issued_at=attempt.query.now, lifetime=lifetime,
            access_token=token.access_token, refresh_token=refresh_token,
            issuer=context.issuer, resource=context.resource, client_id=context.client_id,
            token_endpoint=context.token_endpoint, redirect_uri=context.redirect_uri,
            client_mode=context.client_mode, token_endpoint_auth_method=context.token_endpoint_auth_method,
            requested_scopes=policy.requested_scopes, granted_scopes=granted_scopes,
            configuration_revision=policy.revision,
        ))
