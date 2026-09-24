from importlib import import_module
from typing import Any

__all__ = [
    "APPROVAL_TTL_SECONDS",
    "ApprovalPrincipalProvider",
    "ApprovalStateCodec",
    "CONNECTOR_PUBLICATION_POLLING_BATCH_LIMIT",
    "CONNECTOR_PUBLICATION_POLLING_INTERVAL_SECONDS",
    "ConnectorCapabilityDescriptionOverrideStreamReader",
    "ConnectorPublicationEventHandler",
    "ConnectorPublicationPollingSynchronizer",
    "ConnectorPublicationStreamReader",
    "ConnectorRuntimeState",
    "ConnectorRuntimeStateChangePollingSynchronizer",
    "ConnectorRuntimeStateEventHandler",
    "ConnectorRuntimeStateReader",
    "ConnectorRuntimeStateSink",
    "ConnectorRuntimeStateStreamReader",
    "ConnectorRuntimeStateSynchronizationSource",
    "ConnectorRuntimeStateSynchronizer",
    "CurrentInvocationApprovalPrincipalProvider",
    "DefaultMcpConnectorRuntimeConfig",
    "HttpConnectorCapabilityDescriptionOverrideStreamReader",
    "HttpConnectorPublicationStreamReader",
    "HttpConnectorRuntimeStateReader",
    "HttpConnectorRuntimeStateStreamReader",
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
    "ApprovalPrincipalProvider": ".approval_principal",
    "ApprovalStateCodec": ".approval_state",
    "CONNECTOR_PUBLICATION_POLLING_BATCH_LIMIT": ".publication_events",
    "CONNECTOR_PUBLICATION_POLLING_INTERVAL_SECONDS": ".publication_events",
    "ConnectorCapabilityDescriptionOverrideStreamReader": ".publication_events",
    "ConnectorPublicationEventHandler": ".publication_events",
    "ConnectorPublicationPollingSynchronizer": ".publication_events",
    "ConnectorPublicationStreamReader": ".publication_events",
    "ConnectorRuntimeState": ".runtime_state",
    "ConnectorRuntimeStateChangePollingSynchronizer": ".publication_events",
    "ConnectorRuntimeStateEventHandler": ".publication_events",
    "ConnectorRuntimeStateReader": ".runtime_state",
    "ConnectorRuntimeStateSink": ".runtime_state",
    "ConnectorRuntimeStateStreamReader": ".publication_events",
    "ConnectorRuntimeStateSynchronizationSource": ".runtime_state",
    "ConnectorRuntimeStateSynchronizer": ".runtime_state",
    "CurrentInvocationApprovalPrincipalProvider": ".approval_principal",
    "DefaultMcpConnectorRuntimeConfig": ".default_runtime",
    "HttpConnectorCapabilityDescriptionOverrideStreamReader": ".publication_events",
    "HttpConnectorPublicationStreamReader": ".publication_events",
    "HttpConnectorRuntimeStateReader": ".runtime_state",
    "HttpConnectorRuntimeStateStreamReader": ".publication_events",
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
