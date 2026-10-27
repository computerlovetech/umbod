from unittest.mock import AsyncMock

import pytest

from umbod.core.connectors.downstream_mcp.adapters.fastmcp.oauth import (
    AuthorizationDocument,
    ConnectorOAuth,
    ConnectorOAuthStorage,
    require_sign_in,
)
from umbod.core.connectors.downstream_mcp.personal_connections.runtime_models import (
    PersonalRuntimeUnavailable,
)
from umbod.core.invocation.diagnostics import (
    PERSONAL_RUNTIME_FAILURE,
    InvocationFailureDiagnostic,
)


def test_oauth_options_preserve_background_sign_in_policy() -> None:
    storage = ConnectorOAuthStorage(
        AuthorizationDocument(endpoint_url="https://tools.example/mcp"), "", None
    )
    oauth = ConnectorOAuth(storage)

    assert oauth.context.redirect_handler is require_sign_in
    assert oauth.context.callback_handler is None
    assert str(oauth.context.client_metadata.redirect_uris[0]) == "http://127.0.0.1/oauth/callback"


def test_oauth_options_preserve_interactive_handlers() -> None:
    storage = ConnectorOAuthStorage(
        AuthorizationDocument(endpoint_url="https://tools.example/mcp"), "", None
    )
    redirect_handler = AsyncMock()
    callback_handler = AsyncMock()
    oauth = ConnectorOAuth(
        storage,
        redirect_uri="https://umbod.example/callback",
        redirect_handler=redirect_handler,
        callback_handler=callback_handler,
    )

    assert oauth.context.redirect_handler is redirect_handler
    assert oauth.context.callback_handler is callback_handler
    assert str(oauth.context.client_metadata.redirect_uris[0]) == "https://umbod.example/callback"


def test_oauth_rejects_unknown_options() -> None:
    storage = ConnectorOAuthStorage(
        AuthorizationDocument(endpoint_url="https://tools.example/mcp"), "", None
    )

    with pytest.raises(TypeError):
        ConnectorOAuth(storage, unsupported=True)


def test_runtime_failure_options_preserve_default_diagnostic() -> None:
    error = PersonalRuntimeUnavailable("Personal MCP unavailable")

    assert error.diagnostic == PERSONAL_RUNTIME_FAILURE
    assert str(error) == "Personal MCP unavailable"


def test_runtime_failure_options_preserve_explicit_diagnostic() -> None:
    diagnostic = InvocationFailureDiagnostic(
        execution_mode="personal", stage="transport", reason="timeout"
    )
    error = PersonalRuntimeUnavailable("Personal MCP unavailable", diagnostic=diagnostic)

    assert error.diagnostic == diagnostic


def test_runtime_failure_rejects_unknown_options() -> None:
    with pytest.raises(TypeError):
        PersonalRuntimeUnavailable("Personal MCP unavailable", unsupported=True)
