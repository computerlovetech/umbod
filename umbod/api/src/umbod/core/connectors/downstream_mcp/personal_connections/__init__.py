from importlib import import_module
from typing import TYPE_CHECKING, Any


if TYPE_CHECKING:
    from .health_models import (
        PersonalAuthorizationHealth,
        PersonalAuthorizationHealthQuery,
        PersonalAuthorizationHealthUnavailable,
        RejectPersonalAuthorization,
    )
    from .health_ports import PersonalAuthorizationHealthStore
    from .authorization_models import (
        AbsentPersonalRefreshToken,
        ExpiringPersonalToken,
        PersonalOAuthGrant,
        PresentPersonalRefreshToken,
        UnknownPersonalTokenLifetime,
        authorize_personal_grant,
    )
    from .runtime_models import (
        PersonalAuthorizationRejected,
        PersonalRuntimeAuthorizationQuery,
        PersonalRuntimeTarget,
        PersonalRuntimeUnavailable,
    )
    from .runtime_ports import PersonalMcpTransport, PersonalRuntimeAuthorizationStore
    from .inmemory import InMemoryPersonalConnectionStore
    from .inventory import PersonalConnectorInventoryService
    from .inventory_models import (
        PersonalConnectorQuery,
        PersonalConnectorSelection,
        PersonalConnectorSelections,
        PersonalConnectorUnavailable,
        SetPersonalConnectorEnablement,
    )
    from .inventory_ports import PersonalConnectorInventory
    from .models import (
        Authorized,
        Authorization,
        CanonicalPrincipal,
        MissingCanonicalPrincipal,
        MissingPersonalConnection,
        PersonalConnection,
        PersonalConnectionKey,
        PersonalConnectionState,
        ReplacePersonalAuthorization,
        SetPersonalConnectionEnabled,
        StalePersonalConnectionRevision,
        Unauthorized,
    )
    from .ports import PersonalConnectionStore
    from .caller import PersonalCaller, UnavailablePersonalCaller, PersonalCallerProvider
    from .identity_models import (
        AbsentIssuer,
        MalformedIssuer,
        DeclaredIssuer,
        ObservedIdentityString,
        UnavailableIdentityString,
        PersonalIdentityFacts,
        PersonalIdentityPolicy,
        PersonalIdentityRejection,
        PersonalIdentityResolution,
        ResolvedPersonalIdentity,
        UnresolvedPersonalIdentity,
    )
    from .identity_ports import PersonalIdentityResolver
    from .service import PersonalConnectionService


_EXPORT_MODULES = {
    "PersonalAuthorizationHealth": "health_models",
    "PersonalAuthorizationHealthQuery": "health_models",
    "PersonalAuthorizationHealthUnavailable": "health_models",
    "RejectPersonalAuthorization": "health_models",
    "AbsentPersonalRefreshToken": "authorization_models",
    "ExpiringPersonalToken": "authorization_models",
    "PersonalOAuthGrant": "authorization_models",
    "PresentPersonalRefreshToken": "authorization_models",
    "UnknownPersonalTokenLifetime": "authorization_models",
    "authorize_personal_grant": "authorization_models",
    "PersonalConnectorQuery": "inventory_models",
    "PersonalConnectorSelection": "inventory_models",
    "PersonalConnectorSelections": "inventory_models",
    "PersonalConnectorUnavailable": "inventory_models",
    "SetPersonalConnectorEnablement": "inventory_models",
    "Authorized": "models",
    "Authorization": "models",
    "CanonicalPrincipal": "models",
    "MissingCanonicalPrincipal": "models",
    "MissingPersonalConnection": "models",
    "PersonalConnection": "models",
    "PersonalConnectionKey": "models",
    "PersonalConnectionState": "models",
    "ReplacePersonalAuthorization": "models",
    "SetPersonalConnectionEnabled": "models",
    "StalePersonalConnectionRevision": "models",
    "Unauthorized": "models",
    "AbsentIssuer": "identity_models",
    "MalformedIssuer": "identity_models",
    "DeclaredIssuer": "identity_models",
    "ObservedIdentityString": "identity_models",
    "UnavailableIdentityString": "identity_models",
    "PersonalIdentityFacts": "identity_models",
    "PersonalIdentityPolicy": "identity_models",
    "PersonalIdentityRejection": "identity_models",
    "PersonalIdentityResolution": "identity_models",
    "ResolvedPersonalIdentity": "identity_models",
    "UnresolvedPersonalIdentity": "identity_models",
    "PersonalAuthorizationHealthStore": "health_ports",
    "PersonalAuthorizationRejected": "runtime_models",
    "PersonalRuntimeAuthorizationQuery": "runtime_models",
    "PersonalRuntimeTarget": "runtime_models",
    "PersonalRuntimeUnavailable": "runtime_models",
    "PersonalMcpTransport": "runtime_ports",
    "PersonalRuntimeAuthorizationStore": "runtime_ports",
    "InMemoryPersonalConnectionStore": "inmemory",
    "PersonalConnectorInventoryService": "inventory",
    "PersonalConnectorInventory": "inventory_ports",
    "PersonalCaller": "caller",
    "UnavailablePersonalCaller": "caller",
    "PersonalCallerProvider": "caller",
    "PersonalConnectionStore": "ports",
    "PersonalIdentityResolver": "identity_ports",
    "PersonalConnectionService": "service",
}

__all__ = [
    "PersonalAuthorizationHealth",
    "PersonalAuthorizationHealthQuery",
    "PersonalAuthorizationHealthUnavailable",
    "RejectPersonalAuthorization",
    "PersonalAuthorizationHealthStore",
    "PersonalAuthorizationRejected",
    "AbsentPersonalRefreshToken",
    "ExpiringPersonalToken",
    "PersonalOAuthGrant",
    "PresentPersonalRefreshToken",
    "UnknownPersonalTokenLifetime",
    "authorize_personal_grant",
    "PersonalRuntimeAuthorizationQuery",
    "PersonalRuntimeTarget",
    "PersonalRuntimeUnavailable",
    "PersonalMcpTransport",
    "PersonalRuntimeAuthorizationStore",
    "Authorized",
    "Authorization",
    "CanonicalPrincipal",
    "MissingCanonicalPrincipal",
    "MissingPersonalConnection",
    "PersonalConnection",
    "PersonalConnectionKey",
    "PersonalConnectionState",
    "ReplacePersonalAuthorization",
    "SetPersonalConnectionEnabled",
    "StalePersonalConnectionRevision",
    "Unauthorized",
    "InMemoryPersonalConnectionStore",
    "PersonalCaller",
    "UnavailablePersonalCaller",
    "PersonalCallerProvider",
    "PersonalConnectionStore",
    "PersonalConnectionService",
    "PersonalConnectorInventory",
    "PersonalConnectorInventoryService",
    "PersonalConnectorQuery",
    "PersonalConnectorSelection",
    "PersonalConnectorSelections",
    "PersonalConnectorUnavailable",
    "SetPersonalConnectorEnablement",
    "AbsentIssuer",
    "MalformedIssuer",
    "DeclaredIssuer",
    "ObservedIdentityString",
    "UnavailableIdentityString",
    "PersonalIdentityFacts",
    "PersonalIdentityPolicy",
    "PersonalIdentityRejection",
    "PersonalIdentityResolution",
    "ResolvedPersonalIdentity",
    "UnresolvedPersonalIdentity",
    "PersonalIdentityResolver",
]


def __getattr__(name: str) -> Any:
    module = _EXPORT_MODULES.get(name)
    if module is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(import_module(f".{module}", __name__), name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))
