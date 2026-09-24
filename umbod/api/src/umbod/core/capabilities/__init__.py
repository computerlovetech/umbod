from importlib import import_module
from typing import Any

__all__ = [
    "AbsentCapabilityOutputSchema",
    "AvailabilityAwareCapabilityAuthorizer",
    "CapabilityActivation",
    "CapabilityAvailability",
    "CapabilityCatalog",
    "CapabilityIdentity",
    "CapabilityIdentityConflictError",
    "CapabilityKind",
    "CapabilityNotFoundError",
    "CapabilityPermissionPolicy",
    "CapabilityPublication",
    "CapabilityReadiness",
    "CatalogCapabilityReadiness",
    "ConnectorStoreCapabilityActivation",
    "ConnectorStoreCapabilityPublication",
    "InMemoryCapabilityCatalog",
    "NormalizedCapability",
    "PresentCapabilityOutputSchema",
    "UnrestrictedCapabilityActivation",
    "UnrestrictedCapabilityPermissionPolicy",
    "UnrestrictedCapabilityPublication",
    "UnrestrictedCapabilityReadiness",
]

_EXPORTS: dict[str, str] = {
    "AbsentCapabilityOutputSchema": ".domain",
    "AvailabilityAwareCapabilityAuthorizer": ".availability",
    "CapabilityActivation": ".availability",
    "CapabilityAvailability": ".availability",
    "CapabilityCatalog": ".catalog",
    "CapabilityIdentity": ".domain",
    "CapabilityIdentityConflictError": ".catalog",
    "CapabilityKind": ".domain",
    "CapabilityNotFoundError": ".catalog",
    "CapabilityPermissionPolicy": ".availability",
    "CapabilityPublication": ".availability",
    "CapabilityReadiness": ".availability",
    "CatalogCapabilityReadiness": ".availability",
    "ConnectorStoreCapabilityActivation": ".availability",
    "ConnectorStoreCapabilityPublication": ".availability",
    "InMemoryCapabilityCatalog": ".catalog",
    "NormalizedCapability": ".domain",
    "PresentCapabilityOutputSchema": ".domain",
    "UnrestrictedCapabilityActivation": ".availability",
    "UnrestrictedCapabilityPermissionPolicy": ".availability",
    "UnrestrictedCapabilityPublication": ".availability",
    "UnrestrictedCapabilityReadiness": ".availability",
}


def __getattr__(name: str) -> Any:
    module_name = _EXPORTS.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name}")
    value = getattr(import_module(module_name, __name__), name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(__all__)
