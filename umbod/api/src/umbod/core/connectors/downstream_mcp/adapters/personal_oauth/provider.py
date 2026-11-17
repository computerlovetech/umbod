from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import base64
import hashlib
import json
import re
from datetime import UTC, datetime, timedelta
from collections.abc import Callable

from ...personal_oauth_applications.ports import PersonalOAuthApplicationStore
from ...personal_oauth_applications.models import (
    AbsentApplicationReference, ApplicationReference, ClaimedOAuthApplication, CompleteOAuthApplication,
    ExpiringApplicationSecret, NonexpiringApplicationSecret, OAuthApplicationBinding,
    OAuthApplicationCredentials, RegisteredApplicationReference, ResolveOAuthApplication,
)
from typing import Literal
from urllib.parse import parse_qsl, urlencode, urlsplit

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
from ...personal_connections.oauth_callback_models import (
    GenericBinding, IssuerBinding, PresentCallbackIssuer, issuer_callback_uri, issuer_route_key, validate_callback_binding,
)
from ...personal_connections.models import Authorized
from ...personal_connections.oauth_failure_models import OAuthFailureEvidence, OAuthFailureReason, OAuthFailureStage
from umbod.core.invocation.diagnostics import DownstreamHttpResponse, NoDownstreamResponse
from .failure import OAuthOperationProgress, oauth_failure_boundary, rejected_response, request_with_progress
from ...personal_connections.oauth_models import (
    ExchangePersonalOAuth,
    PersonalOAuthProviderFailure,
    PersonalOAuthProviderUnsupported,
    PreparePersonalOAuth,
    PreparedPersonalOAuth,
)
from ...personal_oauth_configuration.models import (
    PersonalOAuthClient,
    PreconfiguredConfidentialOAuthClient,
    PersonalOAuthPolicy,
    parse_oauth_scopes,
)
from .callback import CallbackURLPolicy, validate_callback_url
from .discovery import authorization_server_metadata, protected_resource_metadata
from .transport import (
    BasicOAuthHttpAuthentication,
    NoOAuthHttpAuthentication,
    OAuthHttpAuthentication,
    OAuthHttpRequest,
    OAuthHttpResponse,
    OAuthHttpTransport,
)
from .validation import (
    AuthorizationServer,
    DiscoveredOAuthServer,
    ProviderContext,
    RegisteredClient,
    RegisteredOAuthClient,
    RegisteredConfidentialOAuthClient,
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
    if client.kind in ("preconfigured_confidential", "dynamic_confidential"):
        return client.token_endpoint_auth_method
    return "none"


def unsupported_configuration(reason: OAuthFailureReason, stage: OAuthFailureStage) -> PersonalOAuthProviderUnsupported:
    return PersonalOAuthProviderUnsupported(OAuthFailureEvidence(
        stage=stage, reason=reason, downstream_response=NoDownstreamResponse(),
    ))


class DiscoveredPersonalOAuthProvider:
    def __init__(self, callback_policy: CallbackURLPolicy, transport: OAuthHttpTransport, applications: PersonalOAuthApplicationStore, clock: Callable[[], datetime]) -> None:
        self._callback_policy = callback_policy
        self._transport = transport
        self._applications = applications
        self._clock = clock

    async def _response(
        self, method: Literal["GET", "POST"], url: str, body: str,
        content_type: str, authentication: OAuthHttpAuthentication, stage: OAuthFailureStage, progress: OAuthOperationProgress,
    ) -> OAuthHttpResponse:
        with oauth_failure_boundary(stage, NoDownstreamResponse()):
            validated_url(url)
            response = await request_with_progress(self._transport, OAuthHttpRequest(
                method=method, url=url, body=SecretStr(body), content_type=content_type,
                authentication=authentication,
            ), progress, stage)
        if response.status not in (200, 201):
            raise rejected_response(stage, response.status)
        return response

    @asynccontextmanager
    async def _request(
        self, method: Literal["GET", "POST"], url: str, body: str,
        content_type: str, authentication: OAuthHttpAuthentication, stage: OAuthFailureStage, progress: OAuthOperationProgress,
    ) -> AsyncIterator[dict[str, object]]:
        response = await self._response(method, url, body, content_type, authentication, stage, progress)
        with oauth_failure_boundary(stage, DownstreamHttpResponse(status_code=response.status)):
            yield parse_json(response.body)

    async def prepare(self, command: PreparePersonalOAuth) -> PreparedPersonalOAuth:
        progress = OAuthOperationProgress(stage="discovery")
        try:
            with anyio.fail_after(60):
                return await self._prepare(command, progress)
        except (PersonalOAuthProviderFailure, PersonalOAuthProviderUnsupported):
            raise
        except ValueError:
            raise PersonalOAuthProviderUnsupported(OAuthFailureEvidence(
                stage=progress.stage, reason="invalid_response", downstream_response=NoDownstreamResponse(),
            )) from None
        except Exception as error:
            raise PersonalOAuthProviderFailure(progress.failure_evidence(error)) from None

    async def _prepare(self, command: PreparePersonalOAuth, progress: OAuthOperationProgress) -> PreparedPersonalOAuth:
        challenge = verifier_digest(command.code_verifier)
        state = command.state.get_secret_value()
        if not state:
            raise ValueError("Invalid state")
        discovered = await self._discover(command.endpoint_url, command.redirect_uri, command.policy, progress, False)
        server = discovered.server
        binding = discovered.callback_binding
        redirect_uri = discovered.redirect_uri
        issuer = server.issuer
        policy = command.policy
        configured_client = policy.client
        auth_method = client_authentication_method(configured_client)
        application_reference: ApplicationReference = AbsentApplicationReference()
        if configured_client.kind == "dynamic_public":
            progress.begin("registration")
            with oauth_failure_boundary("registration", NoDownstreamResponse()):
                registered = await self._register(redirect_uri, policy, server, progress)
                if (
                    "scope" in registered.client.model_fields_set
                    and parse_oauth_scopes(registered.client.scope) != policy.requested_scopes
                ):
                    raise PersonalOAuthProviderUnsupported(OAuthFailureEvidence(
                        stage="registration", reason="scope_mismatch",
                        downstream_response=DownstreamHttpResponse(status_code=registered.status_code),
                    ))
                client_id = registered.client.client_id
        elif configured_client.kind == "dynamic_confidential":
            progress.begin("registration")
            with oauth_failure_boundary("registration", NoDownstreamResponse()):
                application_binding = OAuthApplicationBinding(
                    connector_id=command.connector_id, configuration_revision=policy.revision,
                    issuer=issuer, resource=command.endpoint_url, redirect_uri=redirect_uri,
                    token_endpoint=server.token_endpoint, requested_scopes=policy.requested_scopes,
                    token_endpoint_auth_method=configured_client.token_endpoint_auth_method,
                )
                application = await self._applications.reserve(application_binding)
                if isinstance(application, ClaimedOAuthApplication):
                    registered = await self._register(redirect_uri, policy, server, progress)
                    if not isinstance(registered, RegisteredConfidentialOAuthClient):
                        raise ValueError("Confidential credentials required")
                    application = await self._applications.complete(CompleteOAuthApplication(
                        claim=application, credentials=registered.credentials,
                    ))
                client_id = application.credentials.client_id
                application_reference = RegisteredApplicationReference(registration_id=application.registration_id)
        else:
            client_id = configured_client.client_id
        authorization_parameters = {
            "response_type": "code", "client_id": client_id,
            "redirect_uri": redirect_uri, "state": state,
            "code_challenge": challenge, "code_challenge_method": "S256", "resource": command.endpoint_url,
        }
        if policy.requested_scopes:
            authorization_parameters["scope"] = " ".join(policy.requested_scopes)
        authorization_url = server.authorization_endpoint + "?" + urlencode(authorization_parameters)
        context = ProviderContext(
            issuer=issuer, resource=command.endpoint_url, token_endpoint=server.token_endpoint,
            client_id=client_id, redirect_uri=redirect_uri,
            authorization_url=authorization_url, verifier_digest=challenge,
            state_digest=hashlib.sha256(state.encode()).hexdigest(),
            policy_revision=policy.revision, requested_scopes=list(policy.requested_scopes),
            client_mode=configured_client.kind, token_endpoint_auth_method=auth_method,
            application_reference=application_reference,
        )
        return PreparedPersonalOAuth(
            authorization_url=SecretStr(authorization_url), context=SecretStr(context.model_dump_json()),
            callback_binding=binding,
        )

    async def _discover(
        self, endpoint_url: str, redirect_uri: str, policy: PersonalOAuthPolicy, progress: OAuthOperationProgress,
        select_advertised_issuer: bool,
    ) -> DiscoveredOAuthServer:
        validate_callback_url(redirect_uri, self._callback_policy)
        resource = await protected_resource_metadata(endpoint_url, self._transport, progress)
        with oauth_failure_boundary("discovery", DownstreamHttpResponse(status_code=200)):
            configured_client = policy.client
            auth_method = client_authentication_method(configured_client)
            issuer = resource.authorization_servers[0]
            if configured_client.kind in ("dynamic_public", "dynamic_confidential") and configured_client.approved_issuers:
                issuer = configured_client.approved_issuers[0]
                if issuer not in resource.authorization_servers:
                    raise unsupported_configuration("issuer_mismatch", "discovery")
            elif configured_client.kind in ("dynamic_public", "dynamic_confidential") or select_advertised_issuer:
                if len(resource.authorization_servers) != 1:
                    raise unsupported_configuration("ambiguous_issuer", "discovery")
            else:
                issuer = configured_client.issuer_url
                if issuer not in resource.authorization_servers:
                    raise unsupported_configuration("issuer_mismatch", "discovery")
        server, metadata_status = await authorization_server_metadata(issuer, self._transport, progress)
        with oauth_failure_boundary("discovery", DownstreamHttpResponse(status_code=metadata_status)):
            if auth_method not in server.token_endpoint_auth_methods_supported:
                raise unsupported_configuration("client_auth_required", "discovery")
        binding = (
            GenericBinding(kind="generic", expected_issuer=issuer)
            if server.authorization_response_iss_parameter_supported else IssuerBinding(
                kind="issuer", expected_issuer=issuer,
                issuer_key=issuer_route_key(issuer), redirect_uri=issuer_callback_uri(redirect_uri, issuer),
            )
        )
        effective_redirect = binding.redirect_uri if isinstance(binding, IssuerBinding) else redirect_uri
        return DiscoveredOAuthServer(
            server=server, resource=resource, callback_binding=binding, redirect_uri=effective_redirect,
        )

    async def _register(
        self, redirect_uri: str, policy: PersonalOAuthPolicy, server: AuthorizationServer, progress: OAuthOperationProgress,
    ) -> RegisteredOAuthClient | RegisteredConfidentialOAuthClient:
        if not server.registration_endpoint:
            raise unsupported_configuration("registration_unavailable", "registration")
        validated_url(server.registration_endpoint)
        grant_types = ["authorization_code"] + (
            ["refresh_token"] if "refresh_token" in server.grant_types_supported else []
        )
        registration: dict[str, object] = {
            "client_name": "Umbod",
            "application_type": "native" if redirect_uri.startswith("http://") else "web",
            "redirect_uris": [redirect_uri],
            "token_endpoint_auth_method": client_authentication_method(policy.client),
            "grant_types": grant_types,
            "response_types": ["code"],
        }
        if policy.requested_scopes:
            registration["scope"] = " ".join(policy.requested_scopes)
        response = await self._response(
            "POST", server.registration_endpoint, json.dumps(registration),
            "application/json", NoOAuthHttpAuthentication(), "registration", progress,
        )
        with oauth_failure_boundary("registration", DownstreamHttpResponse(status_code=response.status)):
            raw_client = parse_json(response.body)
            client = RegisteredClient.model_validate(raw_client)
            if (
                (policy.client.kind == "dynamic_public" and "client_secret" in raw_client)
                or client.token_endpoint_auth_method != client_authentication_method(policy.client)
                or client.redirect_uris != [redirect_uri]
                or "authorization_code" not in client.grant_types
                or not set(client.grant_types) <= set(grant_types)
                or client.response_types != ["code"]
                or ("application_type" in raw_client and raw_client["application_type"] != registration["application_type"])
            ):
                raise PersonalOAuthProviderUnsupported(OAuthFailureEvidence(
                    stage="registration", reason="registration_contract_mismatch", downstream_response=NoDownstreamResponse(),
                ))
            if policy.client.kind == "dynamic_confidential":
                if "scope" in raw_client and parse_oauth_scopes(client.scope) != policy.requested_scopes:
                    raise PersonalOAuthProviderUnsupported(OAuthFailureEvidence(
                        stage="registration", reason="scope_mismatch",
                        downstream_response=DownstreamHttpResponse(status_code=response.status),
                    ))
                if "token_endpoint_auth_method" not in raw_client or response.status != 201:
                    raise ValueError("Invalid registration response")
                secret = raw_client.get("client_secret")
                expiry = raw_client.get("client_secret_expires_at")
                if (
                    not isinstance(secret, str) or not 1 <= len(secret) <= 4096
                    or not secret.strip() or any(ord(character) < 32 or ord(character) == 127 for character in secret)
                    or type(expiry) is not int or expiry < 0
                ):
                    raise ValueError("Invalid registered credentials")
                lifetime = NonexpiringApplicationSecret() if expiry == 0 else ExpiringApplicationSecret(expires_at=datetime.fromtimestamp(expiry, UTC))
                if isinstance(lifetime, ExpiringApplicationSecret) and lifetime.expires_at <= self._clock():
                    raise ValueError("Expired registered credentials")
                return RegisteredConfidentialOAuthClient(
                    client=client, status_code=response.status,
                    credentials=OAuthApplicationCredentials(client_id=client.client_id, client_secret=SecretStr(secret), lifetime=lifetime),
                )
            return RegisteredOAuthClient(client=client, status_code=response.status)

    async def exchange(self, command: ExchangePersonalOAuth) -> Authorized:
        progress = OAuthOperationProgress("token_exchange")
        try:
            with anyio.fail_after(20):
                return await self._exchange(command, progress)
        except Exception as error:
            failure = PersonalOAuthProviderFailure(progress.failure_evidence(error))
        raise failure from None

    async def _exchange(self, command: ExchangePersonalOAuth, progress: OAuthOperationProgress) -> Authorized:
        with oauth_failure_boundary("token_exchange", NoDownstreamResponse()):
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
                or (client.kind in ("preconfigured_public", "preconfigured_confidential") and (client.client_id != context.client_id or client.issuer_url != context.issuer))
                or (client.kind in ("dynamic_public", "dynamic_confidential") and client.approved_issuers and context.issuer not in client.approved_issuers)
            ):
                raise ValueError("Invalid policy binding")
            redirect_uri = validate_callback_binding(
                attempt.prepared.callback_binding, attempt.preparation.redirect_uri, command.route, command.issuer,
            )
            binding = attempt.prepared.callback_binding
            if binding.kind != "legacy_generic" and binding.expected_issuer != context.issuer:
                raise ValueError("Invalid context issuer binding")
            if (
                (isinstance(command.issuer, PresentCallbackIssuer) and command.issuer.value != context.issuer)
                or attempt.preparation.endpoint_url != context.resource
                or redirect_uri != context.redirect_uri
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
            validate_callback_url(context.redirect_uri, self._callback_policy)
            for url in (context.issuer, context.resource, context.token_endpoint):
                validated_url(url)
            token_parameters = {
                "grant_type": "authorization_code", "code": command.code.get_secret_value(),
                "redirect_uri": context.redirect_uri,
                "code_verifier": attempt.preparation.code_verifier.get_secret_value(), "resource": context.resource,
            }
            if client.kind == "dynamic_confidential":
                if context.application_reference.kind != "registered":
                    raise ValueError("Application store required")
                if attempt.preparation.connector_id != attempt.query.key.connector_id:
                    raise ValueError("Invalid application owner")
                application = await self._applications.resolve(ResolveOAuthApplication(
                    reference=context.application_reference, client_id=context.client_id,
                    binding=OAuthApplicationBinding(
                        connector_id=attempt.preparation.connector_id, configuration_revision=policy.revision,
                        issuer=context.issuer, resource=context.resource, redirect_uri=context.redirect_uri,
                        token_endpoint=context.token_endpoint, requested_scopes=policy.requested_scopes,
                        token_endpoint_auth_method=client.token_endpoint_auth_method,
                    ),
                ))
                lifetime = application.credentials.lifetime
                if lifetime.kind == "expiring" and lifetime.expires_at <= max(attempt.query.now, self._clock()):
                    raise ValueError("Expired application credentials")
                client = PreconfiguredConfidentialOAuthClient(
                    issuer_url=context.issuer, client_id=context.client_id,
                    token_endpoint_auth_method=client.token_endpoint_auth_method, client_secret=application.credentials.client_secret,
                )
            authentication: OAuthHttpAuthentication = NoOAuthHttpAuthentication()
            if client.kind == "preconfigured_confidential" and client.token_endpoint_auth_method == "client_secret_basic":
                authentication = BasicOAuthHttpAuthentication(client_id=SecretStr(client.client_id), client_secret=client.client_secret)
            else:
                token_parameters["client_id"] = context.client_id
                if client.kind == "preconfigured_confidential":
                    token_parameters["client_secret"] = client.client_secret.get_secret_value()
        async with self._request(
            "POST", context.token_endpoint, urlencode(token_parameters),
            "application/x-www-form-urlencoded", authentication, "token_exchange", progress,
        ) as raw_token:
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
                configuration_revision=policy.revision, application_reference=context.application_reference,
            ))
