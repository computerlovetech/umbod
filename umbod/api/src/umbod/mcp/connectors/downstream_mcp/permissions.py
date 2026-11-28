from typing import Protocol

from fastmcp import FastMCP
from fastmcp.server.dependencies import get_access_token

from umbod.core.callers import AuthenticationProvenance, CallerSnapshot, LegacyGroupClaimPolicy
from umbod.core.permissions import ConnectorCapabilityPermission, InMemoryGroupConnectorToolPermissions
from umbod.core.permissions.domain import GroupPermissionSet
from umbod.mcp.auth.membership import McpAccessTokenAvailability, capture_mcp_caller, restricted_mcp_grants


class DownstreamToolPermissionPolicy(Protocol):
    def allows(self, connector_id: str, operation_name: str) -> bool: ...

    def allows_capability(self, connector_id: str, capability_kind: str, capability_key: str) -> bool: ...


class DownstreamToolPermissionPolicySource(Protocol):
    def capture(self) -> DownstreamToolPermissionPolicy: ...


class CapturedGroupDownstreamToolPermissionPolicy:
    def __init__(self, snapshot: CallerSnapshot, permissions: InMemoryGroupConnectorToolPermissions) -> None:
        self._snapshot = snapshot
        self._permissions = permissions

    def allows(self, connector_id: str, operation_name: str) -> bool:
        return self.allows_capability(connector_id, "tool", operation_name)

    def allows_capability(self, connector_id: str, capability_kind: str, capability_key: str) -> bool:
        if self._snapshot.caller.authentication == AuthenticationProvenance.UNAVAILABLE:
            return False
        return ConnectorCapabilityPermission(
            connector_id=connector_id,
            capability_kind=capability_kind,
            capability_key=capability_key,
        ) in self._permissions.allowed_capabilities(self._snapshot.groups)


class InstanceDownstreamToolPermissionPolicy:
    def __init__(self, grants: GroupPermissionSet) -> None:
        self._capabilities = frozenset(
            (ref.connector_id, ref.capability_kind, ref.capability_key) for ref in grants.capabilities
        )

    def allows(self, connector_id: str, operation_name: str) -> bool:
        return self.allows_capability(connector_id, "tool", operation_name)

    def allows_capability(self, connector_id: str, capability_kind: str, capability_key: str) -> bool:
        return (connector_id, capability_kind, capability_key) in self._capabilities


class GroupDownstreamToolPermissionPolicy:
    def __init__(self, permissions: InMemoryGroupConnectorToolPermissions, server: FastMCP) -> None:
        self._permissions = permissions
        self._server = server

    def capture(self) -> DownstreamToolPermissionPolicy:
        snapshot = capture_mcp_caller(
            self._server, get_access_token() or McpAccessTokenAvailability.UNAVAILABLE, self._permissions.group_claim_fields,
            LegacyGroupClaimPolicy.RUNTIME,
        )
        return CapturedGroupDownstreamToolPermissionPolicy(snapshot, self._permissions)


class InstanceAwareDownstreamToolPermissionPolicy:
    def __init__(self, server: FastMCP, fallback: DownstreamToolPermissionPolicySource) -> None:
        self._server = server
        self._fallback = fallback

    def capture(self) -> DownstreamToolPermissionPolicy:
        grants = restricted_mcp_grants(self._server, get_access_token() or McpAccessTokenAvailability.UNAVAILABLE)
        if grants is not None:
            return InstanceDownstreamToolPermissionPolicy(grants)
        return self._fallback.capture()


class _UnrestrictedCapturedDownstreamToolPermissionPolicy:
    def allows(self, connector_id: str, operation_name: str) -> bool:
        return True

    def allows_capability(self, connector_id: str, capability_kind: str, capability_key: str) -> bool:
        return True


class UnrestrictedDownstreamToolPermissionPolicy:
    def capture(self) -> DownstreamToolPermissionPolicy:
        return _UnrestrictedCapturedDownstreamToolPermissionPolicy()
