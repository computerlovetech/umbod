from collections.abc import Mapping
from fastmcp.server.dependencies import get_access_token, get_server

from umbod.core.capabilities.tools.refs import ConnectorToolRef
from umbod.core.permissions import InMemoryGroupConnectorToolPermissions
from umbod.mcp.connectors.tools.infrastructure.authorization import (
    ConnectorToolAuthorizationScope,
    RestrictedConnectorTools,
    UnrestrictedConnectorTools,
)
from umbod.mcp.connectors.tools.runtime.registry import RuntimeConnectorToolRegistry
from umbod.mcp.connectors.tools.discovery.search import ConnectorToolSearch


def get_connector_tool_search() -> ConnectorToolSearch:
    return get_server().connector_tool_search


def get_connector_tool_registry() -> RuntimeConnectorToolRegistry:
    return get_server().connector_tool_registry


def get_allowed_connector_tool_refs() -> ConnectorToolAuthorizationScope:
    server = get_server()
    permissions: InMemoryGroupConnectorToolPermissions | None = getattr(
        server, "group_connector_tool_permissions", None
    )
    if permissions is None:
        return UnrestrictedConnectorTools()
    token = get_access_token()
    claims = getattr(token, "claims", {}) if token is not None else {}
    if not isinstance(claims, Mapping):
        return RestrictedConnectorTools(frozenset())
    return RestrictedConnectorTools(
        frozenset(
            ConnectorToolRef(permission.connector_id, permission.operation_name)
            for permission in permissions.allowed_tools(claims)
        )
    )
