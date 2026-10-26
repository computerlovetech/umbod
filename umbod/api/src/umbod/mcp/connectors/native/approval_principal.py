from typing import Protocol, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from umbod.core.invocation import ConnectorInvocationDenied
from umbod.mcp.signals import current_mcp_invocation_context


class ApprovalActorIdentity(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    agent_client_id: str
    authenticated_user_id: str

    @model_validator(mode="after")
    def require_identity(self) -> Self:
        if not self.agent_client_id and not self.authenticated_user_id:
            raise ValueError("Approval actor identity requires a client or user")
        return self


class ApprovalSessionIdentity(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    session_id: str = Field(min_length=1)


class ApprovalCallerBinding(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    identity: ApprovalActorIdentity | ApprovalSessionIdentity


class ApprovalCallerCapture(Protocol):
    def capture(self) -> ApprovalCallerBinding: ...


class CurrentInvocationApprovalCallerCapture:
    def capture(self) -> ApprovalCallerBinding:
        invocation_context = current_mcp_invocation_context()
        actor = invocation_context.actor if invocation_context is not None else None
        if actor is None:
            raise ConnectorInvocationDenied("Connector invocation approval requires identity")
        if actor.agent_client_id or actor.authenticated_user_id:
            return ApprovalCallerBinding(
                identity=ApprovalActorIdentity(
                    agent_client_id=actor.agent_client_id or "",
                    authenticated_user_id=actor.authenticated_user_id or "",
                ),
            )
        if actor.session_id:
            return ApprovalCallerBinding(
                identity=ApprovalSessionIdentity(session_id=actor.session_id),
            )
        raise ConnectorInvocationDenied("Connector invocation approval requires identity")


__all__ = [
    "ApprovalActorIdentity",
    "ApprovalCallerBinding",
    "ApprovalCallerCapture",
    "ApprovalSessionIdentity",
    "CurrentInvocationApprovalCallerCapture",
]
