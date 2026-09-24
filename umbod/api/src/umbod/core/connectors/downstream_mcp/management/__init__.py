from importlib import import_module
from typing import Any

__all__ = [
    "ApplyDiscoveredCatalog",
    "ConnectorIdentityAvailability",
    "CreateDownstreamConnectorAggregate",
    "DeleteCatalog",
    "DeleteCredential",
    "DeleteDownstreamConnectorAggregate",
    "DeleteHealth",
    "DeletePublication",
    "DownstreamConnectorCreator",
    "DownstreamConnectorDeleter",
    "DownstreamConnectorIdGenerator",
    "DownstreamConnectorMutationFault",
    "DownstreamConnectorPreparation",
    "DownstreamConnectorQueries",
    "DownstreamConnectorUnitOfWork",
    "DownstreamConnectorUpdater",
    "DownstreamConnectorUnitOfWorkService",
    "InMemoryDownstreamConnectorUnitOfWork",
    "InvalidateDownstreamConnectorAggregate",
    "KeepCatalog",
    "KeepCredential",
    "KeepHealth",
    "PreserveActivation",
    "PreservePublication",
    "ReconcileActivation",
    "ReplaceCatalog",
    "ReplaceCredential",
    "ReplaceDownstreamConnectorAggregate",
    "ReplaceHealth",
    "UnpublishConnector",
    "UpdatePublishedConnectorPrefix",
    "no_downstream_connector_mutation_fault",
    "utc_clock",
]

_EXPORTS: dict[str, str] = {
    "ApplyDiscoveredCatalog": ".unit_of_work",
    "ConnectorIdentityAvailability": ".ports",
    "CreateDownstreamConnectorAggregate": ".unit_of_work",
    "DeleteCatalog": ".unit_of_work",
    "DeleteCredential": ".unit_of_work",
    "DeleteDownstreamConnectorAggregate": ".unit_of_work",
    "DeleteHealth": ".unit_of_work",
    "DeletePublication": ".unit_of_work",
    "DownstreamConnectorCreator": ".create",
    "DownstreamConnectorDeleter": ".delete",
    "DownstreamConnectorIdGenerator": ".ports",
    "DownstreamConnectorMutationFault": ".unit_of_work",
    "DownstreamConnectorPreparation": ".preparation",
    "DownstreamConnectorQueries": ".queries",
    "DownstreamConnectorUnitOfWork": ".unit_of_work",
    "DownstreamConnectorUpdater": ".update",
    "DownstreamConnectorUnitOfWorkService": ".aggregate_unit_of_work",
    "InMemoryDownstreamConnectorUnitOfWork": ".inmemory_unit_of_work",
    "InvalidateDownstreamConnectorAggregate": ".unit_of_work",
    "KeepCatalog": ".unit_of_work",
    "KeepCredential": ".unit_of_work",
    "KeepHealth": ".unit_of_work",
    "PreserveActivation": ".unit_of_work",
    "PreservePublication": ".unit_of_work",
    "ReconcileActivation": ".unit_of_work",
    "ReplaceCatalog": ".unit_of_work",
    "ReplaceCredential": ".unit_of_work",
    "ReplaceDownstreamConnectorAggregate": ".unit_of_work",
    "ReplaceHealth": ".unit_of_work",
    "UnpublishConnector": ".unit_of_work",
    "UpdatePublishedConnectorPrefix": ".unit_of_work",
    "no_downstream_connector_mutation_fault": ".unit_of_work",
    "utc_clock": ".aggregate_unit_of_work",
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
