from urllib.parse import SplitResult, urlunsplit

from pydantic import SecretStr, TypeAdapter

from umbod.core.invocation.diagnostics import DownstreamHttpResponse, NoDownstreamResponse
from ...personal_connections.oauth_failure_models import OAuthFailureEvidence, OAuthFailureReason
from ...personal_connections.oauth_models import PersonalOAuthProviderUnsupported
from ...personal_oauth_configuration.models import OAuthIssuer

from .failure import OAuthOperationProgress, oauth_failure_boundary, rejected_response, request_with_progress
from .validation import AuthorizationServer, ProtectedResource, parse_json, validated_url
from .transport import OAuthDestination, OAuthHttpRequest, OAuthHttpResponse, OAuthHttpTransport


def authorization_server_metadata_urls(issuer: SplitResult) -> tuple[str, ...]:
    issuer_path = issuer.path.rstrip("/")
    paths = (
        "/.well-known/oauth-authorization-server" + issuer_path,
        "/.well-known/openid-configuration" + issuer_path,
    )
    if issuer_path:
        paths += (issuer_path + "/.well-known/openid-configuration",)
    return tuple(urlunsplit((issuer.scheme, issuer.netloc, path, "", "")) for path in paths)


async def authorization_server_metadata_response(
    issuer: SplitResult, transport: OAuthHttpTransport, progress: OAuthOperationProgress,
) -> OAuthHttpResponse:
    for url in authorization_server_metadata_urls(issuer):
        response = await request_with_progress(transport, OAuthHttpRequest(
            method="GET", url=url, content_type="", body=SecretStr(""),
        ), progress, "discovery")
        if response.status != 404:
            break
    return response


def unsupported_metadata(reason: OAuthFailureReason) -> PersonalOAuthProviderUnsupported:
    return PersonalOAuthProviderUnsupported(OAuthFailureEvidence(
        stage="discovery", reason=reason, downstream_response=NoDownstreamResponse(),
    ))


async def protected_resource_metadata(
    endpoint_url: str, transport: OAuthHttpTransport, progress: OAuthOperationProgress,
) -> ProtectedResource:
    with oauth_failure_boundary("discovery", NoDownstreamResponse()):
        endpoint = validated_url(endpoint_url)
        metadata_url = urlunsplit((endpoint.scheme, endpoint.netloc, "/.well-known/oauth-protected-resource" + endpoint.path.rstrip("/"), "", ""))
        response = await request_with_progress(transport, OAuthHttpRequest(
            method="GET", url=metadata_url, content_type="", body=SecretStr(""),
        ), progress, "discovery")
        if response.status == 404 and endpoint.path.rstrip("/"):
            metadata_url = urlunsplit((endpoint.scheme, endpoint.netloc, "/.well-known/oauth-protected-resource", "", ""))
            response = await request_with_progress(transport, OAuthHttpRequest(
                method="GET", url=metadata_url, content_type="", body=SecretStr(""),
            ), progress, "discovery")
    with oauth_failure_boundary("discovery", DownstreamHttpResponse(status_code=response.status)):
        if response.status != 200:
            raise rejected_response("discovery", response.status)
        resource = ProtectedResource.model_validate(parse_json(response.body))
        if resource.resource != endpoint_url:
            raise unsupported_metadata("resource_mismatch")
        if len(set(resource.authorization_servers)) != len(resource.authorization_servers):
            raise ValueError("Duplicate issuers")
        issuer_adapter = TypeAdapter(OAuthIssuer)
        for issuer in resource.authorization_servers:
            issuer_adapter.validate_python(issuer)
            validated_url(issuer)
        return resource


async def authorization_server_metadata(
    issuer: str, transport: OAuthHttpTransport, progress: OAuthOperationProgress,
) -> tuple[AuthorizationServer, int]:
    with oauth_failure_boundary("discovery", NoDownstreamResponse()):
        response = await authorization_server_metadata_response(validated_url(issuer), transport, progress)
    if response.status not in (200, 201):
        raise rejected_response("discovery", response.status)
    with oauth_failure_boundary("discovery", DownstreamHttpResponse(status_code=response.status)):
        server = AuthorizationServer.model_validate(parse_json(response.body))
        requirements: tuple[tuple[bool, OAuthFailureReason], ...] = (
            (server.issuer == issuer, "issuer_mismatch"),
            ("S256" in server.code_challenge_methods_supported, "pkce_s256_required"),
            ("authorization_code" in server.grant_types_supported, "authorization_code_required"),
            ("code" in server.response_types_supported, "code_response_required"),
        )
        for supported, reason in requirements:
            if not supported:
                raise unsupported_metadata(reason)
        for url in (server.authorization_endpoint, server.token_endpoint):
            validated_url(url)
        progress.begin("discovery")
        with oauth_failure_boundary("discovery", NoDownstreamResponse()):
            await transport.validate_destination(OAuthDestination(url=server.authorization_endpoint))
        return server, response.status
