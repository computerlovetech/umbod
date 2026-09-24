from typing import Literal

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field

from umbod.core.identity import ConnectorIdentityConflictError
from umbod.core.capabilities.tools.names import PublicToolNameConflictError
from umbod.core.connectors.downstream_mcp.errors import (
    DownstreamConnectorConflictError,
    DownstreamConnectorNotFoundError,
    DownstreamConnectorUnavailableError,
    DownstreamCredentialMissingError,
    DownstreamPermissionGrantConflict,
    DownstreamPublicPathConflictError,
)
from umbod.core.connectors.downstream_mcp.probe import (
    DownstreamConnectorValidationError,
)

DownstreamMcpErrorPhase = Literal[
    "validation",
    "discovery",
    "identity",
    "publication",
    "permission",
    "credentials",
    "connector",
]
DownstreamMcpErrorCode = Literal[
    "oauth_disabled",
    "endpoint_not_found",
    "auth_rejected",
    "unreachable",
    "timeout",
    "invalid_mcp_protocol",
    "unsafe_redirect",
    "redirect_limit_exceeded",
    "downstream_discovery_failed",
    "connector_not_found",
    "connector_identity_conflict",
    "public_path_conflict",
    "public_tool_name_conflict",
    "downstream_connector_grants_conflict",
    "credential_missing",
    "connector_unavailable",
    "connector_conflict",
    "tool_not_found",
]


class DownstreamMcpErrorDetail(BaseModel):
    model_config = ConfigDict(frozen=True)

    code: DownstreamMcpErrorCode
    message: str
    phase: DownstreamMcpErrorPhase
    retryable: bool = False
    context: dict[str, str | tuple[str, ...]] = Field(default_factory=dict)


def _exception(status_code: int, detail: DownstreamMcpErrorDetail) -> HTTPException:
    return HTTPException(status_code=status_code, detail=detail.model_dump(mode="json"))


def present_downstream_mcp_error(error: Exception) -> HTTPException:
    if isinstance(error, DownstreamConnectorValidationError):
        messages = {
            "oauth_disabled": "Browser sign-in for downstream MCP connections is disabled by configuration.",
            "endpoint_not_found": "No MCP server was found at that endpoint.",
            "auth_rejected": "The downstream server rejected authentication.",
            "unreachable": "The downstream MCP server could not be reached.",
            "timeout": "The downstream MCP server did not respond in time.",
            "invalid_mcp_protocol": "The endpoint did not respond as a valid MCP server.",
            "unsafe_redirect": "The downstream MCP endpoint returned an unsafe redirect.",
            "redirect_limit_exceeded": "The downstream MCP endpoint exceeded the redirect limit.",
        }
        return _exception(
            403 if error.code == "oauth_disabled" else 422,
            DownstreamMcpErrorDetail(
                code=error.code,
                message=messages[error.code],
                phase="validation",
                retryable=error.code in {"unreachable", "timeout"},
            ),
        )
    if isinstance(error, DownstreamConnectorNotFoundError):
        return _exception(
            404,
            DownstreamMcpErrorDetail(
                code="connector_not_found",
                message="Downstream MCP connector not found.",
                phase="connector",
            ),
        )
    if isinstance(error, ConnectorIdentityConflictError):
        return _exception(
            409,
            DownstreamMcpErrorDetail(
                code="connector_identity_conflict",
                message="That connector identity is already in use.",
                phase="identity",
                context={
                    "connector_id": error.requested.connector_id,
                    "existing_type": error.existing.connector_type,
                },
            ),
        )
    if isinstance(error, DownstreamPublicPathConflictError):
        return _exception(
            409,
            DownstreamMcpErrorDetail(
                code="public_path_conflict",
                message="That public path is already in use.",
                phase="identity",
            ),
        )
    if isinstance(error, PublicToolNameConflictError):
        return _exception(
            409,
            DownstreamMcpErrorDetail(
                code="public_tool_name_conflict",
                message="A public tool name conflicts with another connector.",
                phase="publication",
                context={"public_name": error.public_name},
            ),
        )
    if isinstance(error, DownstreamPermissionGrantConflict):
        return _exception(
            409,
            DownstreamMcpErrorDetail(
                code="downstream_connector_grants_conflict",
                message="Remove connector permission grants before deletion.",
                phase="permission",
                context={
                    "connector_id": error.connector_id,
                    "affected_group_ids": error.affected_group_ids,
                },
            ),
        )
    if isinstance(error, DownstreamCredentialMissingError):
        return _exception(
            422,
            DownstreamMcpErrorDetail(
                code="credential_missing",
                message="Connector credentials are not configured.",
                phase="credentials",
            ),
        )
    if isinstance(error, DownstreamConnectorUnavailableError):
        return _exception(
            409,
            DownstreamMcpErrorDetail(
                code="connector_unavailable",
                message="Successful discovery is required before publication.",
                phase="publication",
                retryable=True,
            ),
        )
    if isinstance(error, DownstreamConnectorConflictError):
        return _exception(
            409,
            DownstreamMcpErrorDetail(
                code="connector_conflict",
                message="The connector conflicts with existing configuration.",
                phase="identity",
            ),
        )
    return _exception(
        422,
        DownstreamMcpErrorDetail(
            code="connector_unavailable",
            message="The connector operation is unavailable.",
            phase="connector",
        ),
    )


def present_discovery_failure(connector_id: str) -> HTTPException:
    return _exception(
        502,
        DownstreamMcpErrorDetail(
            code="downstream_discovery_failed",
            message="Downstream MCP discovery failed.",
            phase="discovery",
            retryable=True,
            context={"connector_id": connector_id},
        ),
    )


def present_tool_not_found(connector_id: str, downstream_name: str) -> HTTPException:
    return _exception(
        404,
        DownstreamMcpErrorDetail(
            code="tool_not_found",
            message="Downstream MCP tool not found.",
            phase="connector",
            context={"connector_id": connector_id, "downstream_name": downstream_name},
        ),
    )
