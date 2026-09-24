from typing import Any

from fastmcp.server.dependencies import get_context
from fastmcp.tools import InputRequiredToolResult
from mcp.types import ElicitRequest, ElicitRequestFormParams, ElicitResult, InputRequiredResult
from umbod.core.invocation import (
    ApprovalNonceConsumption,
    ApprovalNonceStore,
)
from umbod.core.invocation import (
    AskInvocationDecision,
    ConnectorInvocation,
    ConnectorInvocationApprovalRequired,
    ConnectorInvocationDecision,
    ConnectorInvocationDenied,
    ConnectorInvocationPolicy,
    DirectInvocationDecision,
)
from umbod.mcp.connectors.approval_principal import ApprovalPrincipalProvider
from umbod.mcp.connectors.approval_state import ApprovalStateCodec


_APPROVAL_REQUEST_KEY = "connector_approval"


class ModernConnectorApprovalRequired(ConnectorInvocationApprovalRequired):
    def __init__(
        self,
        invocation: ConnectorInvocation,
        policy_revision: int,
        result: InputRequiredToolResult,
    ) -> None:
        super().__init__(invocation, policy_revision)
        self.result = result


class McpConnectorInvocationApprovalPolicy(ConnectorInvocationPolicy):
    def __init__(
        self,
        policy: ConnectorInvocationPolicy,
        *,
        nonce_store: ApprovalNonceStore,
        state_codec: ApprovalStateCodec,
        principal_provider: ApprovalPrincipalProvider,
    ) -> None:
        self._policy = policy
        self._nonce_store = nonce_store
        self._state_codec = state_codec
        self._principal_provider = principal_provider

    async def evaluate(self, invocation: ConnectorInvocation) -> ConnectorInvocationDecision:
        decision = await self._policy.evaluate(invocation)
        if not isinstance(decision, AskInvocationDecision):
            return decision
        self._principal_provider()
        context = get_context()
        if context._is_modern_protocol():
            if self._is_codemode_request(context):
                raise ConnectorInvocationDenied("Modern codemode approval is unsupported")
            return await self._evaluate_modern(context, invocation, decision.policy_revision)
        elicitation = await context.elicit(
            self._message(invocation),
            bool,
            response_title="Approve connector invocation",
        )
        if getattr(elicitation, "action", None) != "accept" or getattr(
            elicitation, "data", False
        ) is not True:
            raise ConnectorInvocationDenied("Connector invocation approval denied")
        return DirectInvocationDecision()

    async def _evaluate_modern(
        self, context: Any, invocation: ConnectorInvocation, policy_revision: int
    ) -> ConnectorInvocationDecision:
        request_state = context.request_state
        responses = context.input_responses
        if (request_state is None) != (responses is None):
            raise ConnectorInvocationDenied("Connector invocation continuation is malformed")
        if request_state is None:
            result = InputRequiredToolResult(
                InputRequiredResult(
                    inputRequests={
                        _APPROVAL_REQUEST_KEY: ElicitRequest(
                            params=ElicitRequestFormParams(
                                message=self._message(invocation),
                                requestedSchema={
                                    "type": "object",
                                    "properties": {"value": {"type": "boolean"}},
                                    "required": ["value"],
                                },
                            )
                        )
                    },
                    requestState=self._state_codec.mint(
                        invocation, policy_revision, self._principal_provider()
                    ),
                )
            )
            raise ModernConnectorApprovalRequired(invocation, policy_revision, result)
        response = responses.get(_APPROVAL_REQUEST_KEY)
        if not isinstance(response, ElicitResult):
            raise ConnectorInvocationDenied("Connector invocation approval response invalid")
        if response.action != "accept" or response.content is None:
            raise ConnectorInvocationDenied("Connector invocation approval denied")
        if response.content.get("value") is not True:
            raise ConnectorInvocationDenied("Connector invocation approval denied")
        state = self._state_codec.verify(
            request_state, invocation, policy_revision, self._principal_provider()
        )
        consumed = await self._nonce_store.consume(
            ApprovalNonceConsumption(nonce=state["nonce"], expires_at=state["expires_at"])
        )
        if not consumed:
            raise ConnectorInvocationDenied("Connector invocation approval already consumed")
        return DirectInvocationDecision()

    @staticmethod
    def _is_codemode_request(context: Any) -> bool:
        request_context = context.request_context
        request = getattr(request_context, "request", None)
        params = getattr(request, "params", None)
        return getattr(params, "name", None) == "execute_code"

    @staticmethod
    def _message(invocation: ConnectorInvocation) -> str:
        return f"Approve {invocation.public_tool_name} with the supplied arguments?"


__all__ = [
    "McpConnectorInvocationApprovalPolicy",
    "ModernConnectorApprovalRequired",
]
