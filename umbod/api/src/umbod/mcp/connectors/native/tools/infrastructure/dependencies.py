from collections.abc import Mapping
from fastmcp.server.dependencies import get_access_token, get_server

from umbod.core.callers import AuthenticationProvenance, LegacyGroupClaimPolicy
from umbod.core.capabilities.tools.refs import ConnectorToolRef
from umbod.core.permissions import InMemoryGroupConnectorToolPermissions
from umbod.mcp.auth.caller import authentication_provenance
from umbod.mcp.auth.membership import server_group_membership_resolver
from umbod.mcp.connectors.native.tools.infrastructure.authorization import (
    ConnectorToolAuthorizationScope,
    RestrictedConnectorTools,
    UnrestrictedConnectorTools,
)
from umbod.mcp.connectors.native.tools.runtime.registry import RuntimeConnectorToolRegistry
from umbod.mcp.connectors.native.tools.discovery.search import ConnectorToolSearch


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
    authentication = (
        authentication_provenance(getattr(server, "auth", None))
        if token is not None else AuthenticationProvenance.UNAVAILABLE
    )
    groups = server_group_membership_resolver(server).resolve(
        claims, permissions.group_claim_fields, LegacyGroupClaimPolicy.RUNTIME, authentication,
    )
    return RestrictedConnectorTools(
        frozenset(
            ConnectorToolRef(permission.connector_id, permission.operation_name)
            for permission in permissions.allowed_tools(groups)
        )
    )
