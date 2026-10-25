from collections.abc import Mapping
from typing import Protocol

from fastmcp.server.dependencies import get_access_token, get_server
from pydantic import BaseModel, ConfigDict

from umbod.core.callers import AuthenticationProvenance, CallerContext, GroupMembership
from umbod.core.permissions import ConnectorCapabilityPermission, InMemoryGroupConnectorToolPermissions
from umbod.mcp.auth.caller import authentication_provenance, caller_context_from_access_token
from umbod.mcp.auth.groups import capture_runtime_permission_groups


class DownstreamToolPermissionPolicy(Protocol):
    def allows(self, connector_id: str, operation_name: str) -> bool: ...

    def allows_capability(self, connector_id: str, capability_kind: str, capability_key: str) -> bool: ...


class DownstreamToolPermissionPolicySource(Protocol):
    def capture(self) -> DownstreamToolPermissionPolicy: ...


class DownstreamPermissionSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    caller: CallerContext
    groups: GroupMembership


class CapturedGroupDownstreamToolPermissionPolicy:
    def __init__(self, snapshot: DownstreamPermissionSnapshot, permissions: InMemoryGroupConnectorToolPermissions) -> None:
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


class GroupDownstreamToolPermissionPolicy:
    def __init__(self, permissions: InMemoryGroupConnectorToolPermissions) -> None:
        self._permissions = permissions

    def capture(self) -> DownstreamToolPermissionPolicy:
        token = get_access_token()
        authentication = _current_authentication()
        caller = caller_context_from_access_token(token, authentication)
        observed_claims = getattr(token, "claims", {}) if token is not None else {}
        claims = observed_claims if isinstance(observed_claims, Mapping) else {}
        snapshot = DownstreamPermissionSnapshot(
            caller=caller,
            groups=capture_runtime_permission_groups(claims, self._permissions.group_claim_fields),
        )
        return CapturedGroupDownstreamToolPermissionPolicy(snapshot, self._permissions)


def _current_authentication() -> AuthenticationProvenance:
    try:
        server = get_server()
    except RuntimeError:
        return AuthenticationProvenance.DEPLOYMENT_AUTHENTICATED
    return authentication_provenance(server.auth) if server.auth is not None else AuthenticationProvenance.DEPLOYMENT_AUTHENTICATED


class _UnrestrictedCapturedDownstreamToolPermissionPolicy:
    def allows(self, connector_id: str, operation_name: str) -> bool:
        return True

    def allows_capability(self, connector_id: str, capability_kind: str, capability_key: str) -> bool:
        return True


class UnrestrictedDownstreamToolPermissionPolicy:
    def capture(self) -> DownstreamToolPermissionPolicy:
        return _UnrestrictedCapturedDownstreamToolPermissionPolicy()
