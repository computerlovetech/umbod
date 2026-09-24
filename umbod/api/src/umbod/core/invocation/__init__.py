from importlib import import_module
from typing import Any

__all__ = [
    "APPROVAL_NONCE_TABLE",
    "AskInvocationDecision",
    "ApprovalNonceConsumption",
    "ApprovalNonceStore",
    "CONNECTOR_INVOCATION_POLICY_TABLE",
    "ConnectorInvocation",
    "ConnectorInvocationApprovalRequired",
    "ConnectorInvocationDecision",
    "ConnectorInvocationDenied",
    "ConnectorInvocationPolicy",
    "ConnectorInvocationPolicyConflict",
    "ConnectorInvocationPolicyKey",
    "ConnectorInvocationPolicyRecord",
    "ConnectorInvocationPolicyRevisionConflict",
    "ConnectorInvocationPolicyStore",
    "ConnectorInvocationPolicyUpdate",
    "ConnectorKind",
    "DatabaseApprovalNonceStore",
    "DatabaseConnectorInvocationPolicyStore",
    "DirectInvocationDecision",
    "InMemoryApprovalNonceStore",
    "InvocationPolicyMode",
    "PermitAllConnectorInvocationPolicy",
    "StoredConnectorInvocationPolicy",
    "compare_and_set_invocation_policies",
    "connector_invocation_policy_query",
    "connector_invocation_policy_record",
    "delete_connector_invocation_policies",
    "evaluate_direct_invocation",
]

_EXPORTS: dict[str, str] = {
    "APPROVAL_NONCE_TABLE": ".approval_nonce_store",
    "AskInvocationDecision": ".policy",
    "ApprovalNonceConsumption": ".approval_nonce_store",
    "ApprovalNonceStore": ".approval_nonce_store",
    "CONNECTOR_INVOCATION_POLICY_TABLE": ".policy_store",
    "ConnectorInvocation": ".policy",
    "ConnectorInvocationApprovalRequired": ".policy",
    "ConnectorInvocationDecision": ".policy",
    "ConnectorInvocationDenied": ".policy",
    "ConnectorInvocationPolicy": ".policy",
    "ConnectorInvocationPolicyConflict": ".policy",
    "ConnectorInvocationPolicyKey": ".policy",
    "ConnectorInvocationPolicyRecord": ".policy",
    "ConnectorInvocationPolicyRevisionConflict": ".policy",
    "ConnectorInvocationPolicyStore": ".policy",
    "ConnectorInvocationPolicyUpdate": ".policy",
    "ConnectorKind": ".policy",
    "DatabaseApprovalNonceStore": ".approval_nonce_store",
    "DatabaseConnectorInvocationPolicyStore": ".policy_store",
    "DirectInvocationDecision": ".policy",
    "InMemoryApprovalNonceStore": ".approval_nonce_store",
    "InvocationPolicyMode": ".policy",
    "PermitAllConnectorInvocationPolicy": ".policy",
    "StoredConnectorInvocationPolicy": ".policy",
    "compare_and_set_invocation_policies": ".policy_store",
    "connector_invocation_policy_query": ".policy_store",
    "connector_invocation_policy_record": ".policy_store",
    "delete_connector_invocation_policies": ".policy_store",
    "evaluate_direct_invocation": ".policy",
}


def __getattr__(name: str) -> Any:
    module_name = _EXPORTS.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(import_module(module_name, __name__), name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(__all__)
