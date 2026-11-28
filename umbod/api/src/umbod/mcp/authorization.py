from collections.abc import Awaitable, Callable, Mapping
from typing import Any, cast

from fastmcp import FastMCP
from fastmcp.server.auth import AuthCheck, AuthContext

from umbod.core.callers import LegacyGroupClaimPolicy
from umbod.core.capabilities.domain import CapabilityKind
from umbod.core.permissions import (
    ConnectorCapabilityPermission,
    ConnectorCapabilityRef,
    InMemoryGroupConnectorToolPermissions,
)
from umbod.mcp.auth.agent_tokens import PublicAgentMultiAuth
from umbod.mcp.auth.membership import McpAccessTokenAvailability, capture_mcp_caller, restricted_mcp_grants


class SharedDownstreamCapabilityComponent:
    def group_permission_ref(self, context: AuthContext) -> ConnectorCapabilityRef | None:
        return _capability_ref_from_context(context)


class _AgentCapabilityComponentCheck:
    def __init__(self, server: FastMCP) -> None:
        self._server = server

    def __call__(self, context: AuthContext) -> bool:
        grants = restricted_mcp_grants(self._server, context.token or McpAccessTokenAvailability.UNAVAILABLE)
        if grants is None:
            return True
        ref = _capability_ref_from_context(context)
        return ref is not None and ref in grants.capabilities


class _AgentPlatformToolCheck:
    def __init__(self, server: FastMCP) -> None:
        self._server = server

    def __call__(self, context: AuthContext) -> bool:
        grants = restricted_mcp_grants(self._server, context.token or McpAccessTokenAvailability.UNAVAILABLE)
        return grants is None or bool(grants.group_id)


def agent_capability_component_auth(server: FastMCP) -> AuthCheck | None:
    return _AgentCapabilityComponentCheck(server) if isinstance(getattr(server, "auth", None), PublicAgentMultiAuth) else None


def agent_platform_tool_auth(server: FastMCP) -> AuthCheck | None:
    return _AgentPlatformToolCheck(server) if isinstance(server.auth, PublicAgentMultiAuth) else None


def agent_aware_capability_permission_check(
    server: FastMCP, legacy: Callable[[AuthContext], Awaitable[bool]],
) -> Callable[[AuthContext], Awaitable[bool]]:
    async def check(context: AuthContext) -> bool:
        grants = restricted_mcp_grants(server, context.token or McpAccessTokenAvailability.UNAVAILABLE)
        if grants is None:
            return await legacy(context)
        component_auth = getattr(context.component, "auth", None)
        if isinstance(component_auth, _AgentPlatformToolCheck):
            return bool(grants.group_id)
        if isinstance(context.component, SharedDownstreamCapabilityComponent):
            ref = context.component.group_permission_ref(context)
            return ref is not None and ref in grants.capabilities
        if isinstance(component_auth, _AgentCapabilityComponentCheck):
            ref = _capability_ref_from_context(context)
            return ref is not None and ref in grants.capabilities
        return False

    return check


def connector_capability_permission_check(
    permissions: InMemoryGroupConnectorToolPermissions,
    server: FastMCP,
) -> Callable[[AuthContext], bool]:
    def check(context: AuthContext) -> bool:
        ref = _capability_ref_from_context(context)
        if ref is None:
            return True
        access_token = context.token
        if access_token is None:
            return False
        caller = capture_mcp_caller(
            server, access_token, permissions.group_claim_fields, LegacyGroupClaimPolicy.RUNTIME,
        )
        return ConnectorCapabilityPermission(
            connector_id=ref.connector_id,
            capability_kind=ref.capability_kind,
            capability_key=ref.capability_key,
        ) in permissions.allowed_capabilities(caller.groups)

    return check


def _capability_ref_from_context(context: AuthContext) -> ConnectorCapabilityRef | None:
    tool = context.tool
    if tool is not None:
        metadata = tool.get_meta()
        connector_id = metadata.get("connector_id") if isinstance(metadata, Mapping) else None
        operation_name = metadata.get("operation_name") if isinstance(metadata, Mapping) else None
        if isinstance(connector_id, str) and isinstance(operation_name, str):
            return ConnectorCapabilityRef(
                connector_id=connector_id,
                capability_kind="tool",
                capability_key=operation_name,
            )
        return None

    component = getattr(context, "component", None)
    if component is None:
        return None
    metadata = _component_meta(component)
    connector_id = metadata.get("connector_id")
    capability_kind = metadata.get("capability_kind")
    capability_key = metadata.get("capability_key") or metadata.get("operation_name")
    if (
        isinstance(connector_id, str)
        and isinstance(capability_kind, str)
        and isinstance(capability_key, str)
        and capability_kind in {"tool", "prompt", "resource", "resource_template"}
    ):
        return ConnectorCapabilityRef(
            connector_id=connector_id,
            capability_kind=cast(CapabilityKind, capability_kind),
            capability_key=capability_key,
        )
    return None


def _component_meta(component: Any) -> Mapping[str, object]:
    get_meta = getattr(component, "get_meta", None)
    if callable(get_meta):
        metadata = get_meta()
        if isinstance(metadata, Mapping):
            return metadata
    metadata = getattr(component, "meta", None)
    if isinstance(metadata, Mapping):
        return metadata
    return {}
