from importlib import import_module
from typing import TYPE_CHECKING, Any


if TYPE_CHECKING:
    from umbod.core.connectors.downstream_mcp.activation import (
        DownstreamActivationEventPublicationPolicy,
        DownstreamConnectorActivation,
    )
    from umbod.core.connectors.downstream_mcp.catalog import (
        DownstreamCapabilityRecord,
        DownstreamConnectorCatalogLifecycle,
        StoreBackedDownstreamCapabilityCatalog,
    )
    from umbod.core.connectors.downstream_mcp.connection import (
        DownstreamMcpConnectionConfiguration,
        NoAuthConnectionConfiguration,
        OAuthConnectionConfiguration,
        StaticBearerConnectionConfiguration,
        connection_configuration_from_persisted_models,
    )
    from umbod.core.connectors.downstream_mcp.errors import (
        DownstreamConnectorConflictError,
        DownstreamConnectorNotFoundError,
        DownstreamConnectorUnavailableError,
        DownstreamCredentialMissingError,
        DownstreamPermissionGrantConflict,
        DownstreamPublicPathConflictError,
    )
    from umbod.core.connectors.downstream_mcp.management import (
        DownstreamConnectorCreator,
        DownstreamConnectorDeleter,
        DownstreamConnectorPreparation,
        DownstreamConnectorQueries,
        DownstreamConnectorUpdater,
    )
    from umbod.core.connectors.downstream_mcp.models import (
        CatalogReconciliation,
        ConnectorHealthy,
        ConnectorUnhealthy,
        CreateConnectorDefinition,
        CreatePersonalOAuthConnectorDefinition,
        DiscoveryFailed,
        DiscoveryResult,
        DiscoverySucceeded,
        PreparedCatalogConnector,
        ToolCatalogSnapshot,
    )
    from umbod.core.connectors.downstream_mcp.probe import (
        DiscoverDownstreamTools,
        DownstreamDiscovery,
        DownstreamMcpProbe,
        ProbeResult,
    )
    from umbod.core.connectors.downstream_mcp.publishing import (
        DownstreamConnectorPublisher,
    )
    from umbod.core.connectors.downstream_mcp.security import (
        resolve_downstream_mcp_credential_secret,
    )


_EXPORT_MODULES = {
    "DownstreamActivationEventPublicationPolicy": "activation",
    "DownstreamConnectorActivation": "activation",
    "DownstreamCapabilityRecord": "catalog",
    "DownstreamConnectorCatalogLifecycle": "catalog",
    "StoreBackedDownstreamCapabilityCatalog": "catalog",
    "DownstreamMcpConnectionConfiguration": "connection",
    "NoAuthConnectionConfiguration": "connection",
    "OAuthConnectionConfiguration": "connection",
    "StaticBearerConnectionConfiguration": "connection",
    "connection_configuration_from_persisted_models": "connection",
    "DownstreamConnectorConflictError": "errors",
    "DownstreamConnectorNotFoundError": "errors",
    "DownstreamConnectorUnavailableError": "errors",
    "DownstreamCredentialMissingError": "errors",
    "DownstreamPermissionGrantConflict": "errors",
    "DownstreamPublicPathConflictError": "errors",
    "DownstreamConnectorCreator": "management",
    "DownstreamConnectorDeleter": "management",
    "DownstreamConnectorPreparation": "management",
    "DownstreamConnectorQueries": "management",
    "DownstreamConnectorUpdater": "management",
    "CatalogReconciliation": "models",
    "ConnectorHealthy": "models",
    "ConnectorUnhealthy": "models",
    "CreateConnectorDefinition": "models",
    "CreatePersonalOAuthConnectorDefinition": "models",
    "DiscoveryFailed": "models",
    "DiscoveryResult": "models",
    "DiscoverySucceeded": "models",
    "PreparedCatalogConnector": "models",
    "ToolCatalogSnapshot": "models",
    "DiscoverDownstreamTools": "probe",
    "DownstreamDiscovery": "probe",
    "DownstreamMcpProbe": "probe",
    "ProbeResult": "probe",
    "DownstreamConnectorPublisher": "publishing",
    "resolve_downstream_mcp_credential_secret": "security",
}

__all__ = [
    "CatalogReconciliation",
    "ConnectorHealthy",
    "ConnectorUnhealthy",
    "CreateConnectorDefinition",
    "CreatePersonalOAuthConnectorDefinition",
    "DiscoverDownstreamTools",
    "DiscoveryFailed",
    "DiscoveryResult",
    "DiscoverySucceeded",
    "DownstreamActivationEventPublicationPolicy",
    "DownstreamConnectorActivation",
    "DownstreamCapabilityRecord",
    "DownstreamConnectorCatalogLifecycle",
    "DownstreamConnectorConflictError",
    "DownstreamConnectorCreator",
    "DownstreamConnectorDeleter",
    "DownstreamConnectorNotFoundError",
    "DownstreamConnectorPreparation",
    "DownstreamConnectorPublisher",
    "DownstreamConnectorQueries",
    "DownstreamConnectorUnavailableError",
    "DownstreamConnectorUpdater",
    "DownstreamCredentialMissingError",
    "DownstreamDiscovery",
    "DownstreamMcpConnectionConfiguration",
    "DownstreamMcpProbe",
    "DownstreamPermissionGrantConflict",
    "DownstreamPublicPathConflictError",
    "NoAuthConnectionConfiguration",
    "OAuthConnectionConfiguration",
    "PreparedCatalogConnector",
    "ProbeResult",
    "StaticBearerConnectionConfiguration",
    "StoreBackedDownstreamCapabilityCatalog",
    "ToolCatalogSnapshot",
    "connection_configuration_from_persisted_models",
    "resolve_downstream_mcp_credential_secret",
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
