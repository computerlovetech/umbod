import hashlib
import json
import secrets
from collections.abc import Callable, Mapping
from typing import Any, TypedDict

from pydantic_core import to_jsonable_python

from umbod.core.invocation import (
    ConnectorInvocation,
    ConnectorInvocationDenied,
)


APPROVAL_TTL_SECONDS = 300


class VerifiedApprovalState(TypedDict):
    nonce: str
    expires_at: int


class ApprovalStateCodec:
    def __init__(
        self,
        *,
        clock: Callable[[], float],
        random_token: Callable[[], str],
        ttl_seconds: int,
    ) -> None:
        self._clock = clock
        self._random_token = random_token
        self._ttl_seconds = ttl_seconds

    def mint(
        self,
        invocation: ConnectorInvocation,
        policy_revision: int,
        principal: Mapping[str, str],
    ) -> str:
        payload = {
            "arguments_digest": self.arguments_digest(invocation.arguments),
            "connector_id": invocation.connector_id,
            "connector_kind": invocation.connector_kind,
            "expires_at": int(self._clock()) + self._ttl_seconds,
            "nonce": self._random_token(),
            "operation_name": invocation.operation_name,
            "policy_revision": policy_revision,
            "principal": dict(principal),
            "public_tool_name": invocation.public_tool_name,
        }
        return json.dumps(payload, separators=(",", ":"), sort_keys=True)

    def verify(
        self,
        token: str,
        invocation: ConnectorInvocation,
        policy_revision: int,
        principal: Mapping[str, str],
    ) -> VerifiedApprovalState:
        try:
            payload = json.loads(token)
        except (TypeError, json.JSONDecodeError) as error:
            raise ConnectorInvocationDenied("Connector invocation approval state invalid") from error
        expected = {
            "arguments_digest": self.arguments_digest(invocation.arguments),
            "connector_id": invocation.connector_id,
            "connector_kind": invocation.connector_kind,
            "operation_name": invocation.operation_name,
            "policy_revision": policy_revision,
            "principal": dict(principal),
            "public_tool_name": invocation.public_tool_name,
        }
        required_keys = {*expected, "expires_at", "nonce"}
        if (
            not isinstance(payload, dict)
            or set(payload) != required_keys
            or any(payload.get(key) != value for key, value in expected.items())
        ):
            raise ConnectorInvocationDenied("Connector invocation approval state invalid")
        expires_at = payload.get("expires_at")
        nonce = self.extract_nonce(payload)
        if not isinstance(expires_at, int) or isinstance(expires_at, bool):
            raise ConnectorInvocationDenied("Connector invocation approval state invalid")
        if self._clock() > expires_at:
            raise ConnectorInvocationDenied("Connector invocation approval state expired")
        return {"nonce": nonce, "expires_at": expires_at}

    @staticmethod
    def extract_nonce(payload: Mapping[str, Any]) -> str:
        nonce = payload.get("nonce")
        if not isinstance(nonce, str) or not nonce:
            raise ConnectorInvocationDenied("Connector invocation approval state invalid")
        return nonce

    @staticmethod
    def arguments_digest(arguments: Mapping[str, Any]) -> str:
        serialized = json.dumps(
            to_jsonable_python(dict(arguments)),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode()
        return hashlib.sha256(serialized).hexdigest()


def random_approval_token() -> str:
    return secrets.token_urlsafe(24)


__all__ = [
    "APPROVAL_TTL_SECONDS",
    "ApprovalStateCodec",
    "VerifiedApprovalState",
    "random_approval_token",
]
