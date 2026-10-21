from importlib import import_module
from typing import Any

__all__ = [
    "ConnectorTelemetryInterceptor",
    "ConnectorToolChangePollingSynchronizer",
    "ConnectorToolChangeStreamReader",
    "ConnectorToolErrorFormatter",
    "ConnectorToolInvocationIdentity",
    "ConnectorToolMapping",
    "ConnectorToolRuntimeStateSynchronizer",
    "ConnectorToolSearchCandidate",
    "HttpConnectorToolChangeStreamReader",
    "HttpConnectorToolRuntimeStateReader",
    "InMemoryConnectorToolRuntimeStateStore",
    "RuntimeConnectorToolRegistry",
    "RuntimeReconciliationResult",
    "install_tool_list_changed_notifier",
    "register_connector_tools",
]

_EXPORTS: dict[str, str] = {
    "ConnectorTelemetryInterceptor": ".invocation.telemetry",
    "ConnectorToolChangePollingSynchronizer": ".runtime.synchronization",
    "ConnectorToolChangeStreamReader": ".runtime.synchronization",
    "ConnectorToolErrorFormatter": ".invocation.errors",
    "ConnectorToolInvocationIdentity": ".invocation.lifecycle",
    "ConnectorToolMapping": "umbod.core.connectors.native.runtime.tools",
    "ConnectorToolRuntimeStateSynchronizer": ".runtime.synchronization",
    "ConnectorToolSearchCandidate": ".discovery.search",
    "HttpConnectorToolChangeStreamReader": ".infrastructure.http_clients",
    "HttpConnectorToolRuntimeStateReader": ".infrastructure.http_clients",
    "InMemoryConnectorToolRuntimeStateStore": ".runtime.state",
    "RuntimeConnectorToolRegistry": ".runtime.registry",
    "RuntimeReconciliationResult": ".runtime.ports",
    "install_tool_list_changed_notifier": ".infrastructure.client_notifications",
    "register_connector_tools": ".registration",
}


def __getattr__(name: str) -> Any:
    module_name = _EXPORTS.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    if module_name.startswith("."):
        value = getattr(import_module(module_name, __name__), name)
    else:
        value = getattr(import_module(module_name), name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted({*globals(), *__all__})
