from importlib import import_module
from typing import Any

__all__ = [
    "ActivationBatchResult",
    "ActivationCatalog",
    "ActivationError",
    "ActivationFailure",
    "ActivationFilter",
    "ActivationListFilter",
    "ActivationNotifier",
    "ActivationPort",
    "ActivationResult",
    "ActivationStatus",
    "ActivationStore",
    "CAPABILITY_ACTIVATION_STATE_TABLE",
    "CapabilityActivationService",
    "CapabilityActivationState",
    "CapabilityKind",
    "CapabilityRef",
    "CapabilitySourceActivationCatalog",
    "InMemoryActivationNotifier",
    "InMemoryActivationStore",
    "KeySetActivationCatalog",
    "create_capability_activation_store",
]

_EXPORTS: dict[str, str] = {
    "ActivationBatchResult": ".domain",
    "ActivationCatalog": ".domain",
    "ActivationError": ".domain",
    "ActivationFailure": ".domain",
    "ActivationFilter": ".domain",
    "ActivationListFilter": ".domain",
    "ActivationNotifier": ".domain",
    "ActivationPort": ".domain",
    "ActivationResult": ".domain",
    "ActivationStatus": ".domain",
    "ActivationStore": ".domain",
    "CAPABILITY_ACTIVATION_STATE_TABLE": ".stores.schema",
    "CapabilityActivationService": ".service",
    "CapabilityActivationState": ".domain",
    "CapabilityKind": "umbod.core.capabilities.domain",
    "CapabilityRef": ".domain",
    "CapabilitySourceActivationCatalog": ".catalog",
    "InMemoryActivationNotifier": ".service",
    "InMemoryActivationStore": ".service",
    "KeySetActivationCatalog": ".catalog",
    "create_capability_activation_store": ".factories",
}


def __getattr__(name: str) -> Any:
    module_name = _EXPORTS.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name}")
    if module_name.startswith("."):
        value = getattr(import_module(module_name, __name__), name)
    else:
        value = getattr(import_module(module_name), name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(__all__)
