from collections.abc import Mapping
from typing import Protocol

from umbod.core.invocation import ConnectorInvocationDenied
from umbod.mcp.logging import current_mcp_invocation_context


class ApprovalPrincipalProvider(Protocol):
    def __call__(self) -> Mapping[str, str]: ...


class CurrentInvocationApprovalPrincipalProvider:
    def __call__(self) -> Mapping[str, str]:
        invocation_context = current_mcp_invocation_context()
        actor = invocation_context.actor if invocation_context is not None else None
        components = {
            "agent_client_id": actor.agent_client_id if actor is not None else None,
            "authenticated_user_id": actor.authenticated_user_id if actor is not None else None,
        }
        principal = {key: value for key, value in components.items() if value}
        if not principal and actor is not None and actor.session_id:
            principal = {"session_id": actor.session_id}
        if not principal:
            raise ConnectorInvocationDenied("Connector invocation approval requires identity")
        return principal


__all__ = ["ApprovalPrincipalProvider", "CurrentInvocationApprovalPrincipalProvider"]
