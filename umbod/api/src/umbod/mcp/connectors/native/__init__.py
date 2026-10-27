from importlib import import_module
from typing import Any

__all__ = [
    "APPROVAL_TTL_SECONDS",
    "ApprovalCallerBinding",
    "ApprovalCallerCapture",
    "ApprovalStateCodec",
    "ConnectorRuntimeState",
    "ConnectorRuntimeStateReader",
    "ConnectorRuntimeStateSink",
    "ConnectorRuntimeStateSynchronizationSource",
    "ConnectorRuntimeStateSynchronizer",
    "CurrentInvocationApprovalCallerCapture",
    "DefaultMcpConnectorRuntimeConfig",
    "HttpConnectorRuntimeStateReader",
    "HttpConnectorRuntimeStateSynchronizationSource",
    "LocalConnectorRuntimeStateSynchronizationSource",
    "McpConnectorInvocationApprovalPolicy",
    "ModernConnectorApprovalRequired",
    "RuntimeConnectorToolReconciler",
    "SQLiteConnectorRuntimeStateReader",
    "StoreBackedConnectorRuntimeStateReader",
    "StoreBackedConnectorRuntimeStateSynchronizationSource",
    "VerifiedApprovalState",
    "create_default_mcp_connector_runtime",
    "create_default_mcp_connector_runtime_from_environment",
    "random_approval_token",
]

_EXPORTS: dict[str, str] = {
    "APPROVAL_TTL_SECONDS": ".approval_state",
    "ApprovalCallerBinding": ".approval_principal",
    "ApprovalCallerCapture": ".approval_principal",
    "ApprovalStateCodec": ".approval_state",
    "ConnectorRuntimeState": ".runtime_state",
    "ConnectorRuntimeStateReader": ".runtime_state",
    "ConnectorRuntimeStateSink": ".runtime_state",
    "ConnectorRuntimeStateSynchronizationSource": ".runtime_state",
    "ConnectorRuntimeStateSynchronizer": ".runtime_state",
    "CurrentInvocationApprovalCallerCapture": ".approval_principal",
    "DefaultMcpConnectorRuntimeConfig": ".default_runtime",
    "HttpConnectorRuntimeStateReader": ".runtime_state",
    "HttpConnectorRuntimeStateSynchronizationSource": ".runtime_state",
    "LocalConnectorRuntimeStateSynchronizationSource": ".runtime_state",
    "McpConnectorInvocationApprovalPolicy": ".approval",
    "ModernConnectorApprovalRequired": ".approval",
    "RuntimeConnectorToolReconciler": ".runtime_state",
    "SQLiteConnectorRuntimeStateReader": ".runtime_state",
    "StoreBackedConnectorRuntimeStateReader": ".runtime_state",
    "StoreBackedConnectorRuntimeStateSynchronizationSource": ".runtime_state",
    "VerifiedApprovalState": ".approval_state",
    "create_default_mcp_connector_runtime": ".default_runtime",
    "create_default_mcp_connector_runtime_from_environment": ".default_runtime",
    "random_approval_token": ".approval_state",
}


def __getattr__(name: str) -> Any:
    module_name = _EXPORTS.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(import_module(module_name, __name__), name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted({*globals(), *__all__})
