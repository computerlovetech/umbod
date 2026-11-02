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


def protected_rest_request(scope: Scope) -> bool:
    path = get_route_path(scope)
    return (
        within_namespace(path, "/api")
        and path not in (
            "/api/system/health",
            "/api/oauth/downstream-mcp/docs",
            "/api/oauth/downstream-mcp/openapi.json",
        )
        and not within_namespace(path, "/api/oauth/downstream-mcp/callback")
    )
