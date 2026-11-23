import re

from starlette._utils import get_route_path
from starlette.types import Scope


def within_namespace(path: str, namespace: str) -> bool:
    return path == namespace or path.startswith(namespace + "/")


def delegated_upload_request(scope: Scope) -> bool:
    return scope["method"] == "PUT" and re.fullmatch(
        r"/api/filesystem/uploads/[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}/transfer",
        get_route_path(scope),
    ) is not None


def install_claim_redemption_request(scope: Scope) -> bool:
    return scope["method"] == "POST" and get_route_path(scope) in (
        "/api/install/v1/codex/telemetry/redeem",
        "/api/install/v1/claude-code/telemetry/redeem",
    )


def protected_rest_request(scope: Scope) -> bool:
    path = get_route_path(scope)
    return (
        within_namespace(path, "/api")
        and path not in (
            "/api/system/health",
            "/api/oauth/downstream-mcp/docs",
            "/api/oauth/downstream-mcp/openapi.json",
        )
        and not (
            scope["method"] in {"GET", "HEAD"}
            and re.fullmatch(
                r"/api/install/v1/(?:codex|claude-code)/(?:package\.zip|package\.sha256|marketplace\.txt|endpoint\.txt|install\.sh|install\.ps1)",
                path,
            ) is not None
        )
        and not install_claim_redemption_request(scope)
        and not within_namespace(path, "/api/oauth/downstream-mcp/callback")
    )
