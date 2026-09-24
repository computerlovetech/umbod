from collections.abc import Callable

import pytest
from fastapi import HTTPException

from umbod.core.identity import ConnectorIdentity, ConnectorIdentityConflictError
from umbod.core.connectors.downstream_mcp.errors import (
    DownstreamConnectorNotFoundError,
    DownstreamCredentialMissingError,
    DownstreamPublicPathConflictError,
)
from umbod.core.connectors.downstream_mcp.probe import (
    DownstreamConnectorValidationError,
    DownstreamConnectorValidationFailed,
)
from umbod.rest.connectors.downstream_mcp.errors import present_downstream_mcp_error


def _identity_conflict() -> Exception:
    return ConnectorIdentityConflictError(
        ConnectorIdentity(connector_id="one", connector_type="downstream_mcp"),
        ConnectorIdentity(connector_id="one", connector_type="openapi"),
    )


@pytest.mark.parametrize(
    ("error_factory", "status_code", "code"),
    [
        (
            lambda: DownstreamConnectorValidationError(
                DownstreamConnectorValidationFailed(code="timeout")
            ),
            422,
            "timeout",
        ),
        (lambda: DownstreamConnectorNotFoundError("one"), 404, "connector_not_found"),
        (_identity_conflict, 409, "connector_identity_conflict"),
        (
            lambda: DownstreamPublicPathConflictError("/mcp/proxies/one"),
            409,
            "public_path_conflict",
        ),
        (lambda: DownstreamCredentialMissingError("one"), 422, "credential_missing"),
    ],
)
def test_presenter_maps_known_errors_to_stable_safe_envelopes(
    error_factory: Callable[[], Exception], status_code: int, code: str
) -> None:
    source = error_factory()
    presented = present_downstream_mcp_error(source)
    assert isinstance(presented, HTTPException)
    assert presented.status_code == status_code
    assert presented.detail["code"] == code
    assert "private-provider-cause" not in str(presented.detail)
    assert "secret" not in str(presented.detail).lower()
