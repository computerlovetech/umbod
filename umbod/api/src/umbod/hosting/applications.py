from dataclasses import replace
from typing import Optional, Sequence

from fastapi import FastAPI
from starlette.applications import Starlette

from umbod.hosting.contracts import (
    AppConfig,
    ConnectorRegistration,
    InMemoryGroupConnectorToolPermissions,
    JwtVerifier,
    MCPAuthProvider,
    McpToolInvocationLogSink,
    OAuthService,
)
from umbod.mcp.public_app import (
    build_starlette_app,
    create_runtime_context,
    load_configured_public_app_config,
)
from umbod.rest.main import create_app as _create_rest_app


def create_rest_app(
    settings: AppConfig,
    *,
    connector_registrations: Optional[Sequence[ConnectorRegistration]],
    admin_verifier: Optional[JwtVerifier],
    oauth_service: Optional[OAuthService],
    **user_authentication: object,
) -> FastAPI:
    unknown_keywords = set(user_authentication) - {"user_verifier"}
    if unknown_keywords:
        keyword = next(iter(unknown_keywords))
        raise TypeError(f"create_rest_app() got an unexpected keyword argument '{keyword}'")
    return _create_rest_app(
        settings,
        connector_registrations=connector_registrations,
        admin_verifier=admin_verifier,
        oauth_service=oauth_service,
        user_verifier=user_authentication.get("user_verifier"),
    )


async def create_mcp_app(
    settings: AppConfig,
    *,
    auth_provider: Optional[MCPAuthProvider],
    group_permission_runtime_state: Optional[InMemoryGroupConnectorToolPermissions],
    invocation_log_sink: Optional[McpToolInvocationLogSink],
) -> Starlette:
    config = await load_configured_public_app_config(settings)
    try:
        if auth_provider is not None:
            config = replace(config, auth_provider=auth_provider)
        if group_permission_runtime_state is not None:
            config = replace(config, group_permission_runtime_state=group_permission_runtime_state)
        if invocation_log_sink is not None:
            config = replace(config, invocation_log_sink=invocation_log_sink)
        return await build_starlette_app(await create_runtime_context(config))
    except BaseException:
        await config.persistence_runtime.shutdown()
        raise
