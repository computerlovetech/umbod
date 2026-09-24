from collections.abc import Callable
from dataclasses import dataclass

from umbod.core.publishing import ConnectorPublishingStore
from umbod.core.activation import ActivationStore
from umbod.core.connectors.downstream_mcp.stores import (
    ConnectorDefinitionStore,
    ConnectorHealthStore,
    EncryptedCredentialStore,
    ToolCatalogStore,
)
from umbod.core.connectors.downstream_mcp.probe import DownstreamDiscovery
from umbod.mcp.downstream_mcp_connectors.capability_notifications import (
    CapabilityListChangeNotifier,
    NativeCapabilityChangeMonitor,
    NativeCapabilityProjection,
)
from umbod.mcp.downstream_mcp_connectors.catalog_reconciliation import (
    CatalogReconciliationDependencies,
    DiscoveredCatalogReconciler,
)
from umbod.mcp.downstream_mcp_connectors.discovery_execution import (
    BoundedConnectorDiscoveryRefresher,
    ConfiguredConnectorRefresher,
    ConnectorDiscoveryExecutionDependencies,
    ConnectorDiscoveryExecutor,
)
from umbod.mcp.downstream_mcp_connectors.discovery_scheduling import (
    ConnectorDiscoverySchedule,
    ConnectorDiscoveryScheduleOptions,
    PeriodicDiscoveryRunner,
)


@dataclass(frozen=True)
class DownstreamDiscoveryCoordinatorOptions:
    refresh_interval_seconds: float
    maximum_concurrency: int
    jitter_ratio: float
    maximum_backoff_seconds: float

    def __post_init__(self) -> None:
        if self.refresh_interval_seconds <= 0:
            raise ValueError("refresh interval must be positive")
        if self.maximum_concurrency <= 0:
            raise ValueError("maximum concurrency must be positive")
        if not 0 <= self.jitter_ratio <= 1:
            raise ValueError("jitter ratio must be between zero and one")
        if self.maximum_backoff_seconds < self.refresh_interval_seconds:
            raise ValueError("maximum backoff must not be less than refresh interval")


@dataclass(frozen=True)
class DownstreamDiscoveryStores:
    definitions: ConnectorDefinitionStore
    credentials: EncryptedCredentialStore
    catalogs: ToolCatalogStore
    health: ConnectorHealthStore
    activations: ActivationStore
    publishing: ConnectorPublishingStore


@dataclass(frozen=True)
class DownstreamDiscoveryAdapters:
    discovery: DownstreamDiscovery
    notifier: CapabilityListChangeNotifier
    native_capabilities: NativeCapabilityProjection
    monotonic_clock: Callable[[], float]
    random_source: Callable[[], float]


@dataclass(frozen=True)
class DownstreamDiscoveryComponents:
    runner: PeriodicDiscoveryRunner
    configured_refresher: ConfiguredConnectorRefresher
    connector_refresher: BoundedConnectorDiscoveryRefresher
    native_monitor: NativeCapabilityChangeMonitor


class DownstreamDiscoveryCoordinator:
    def __init__(self, components: DownstreamDiscoveryComponents) -> None:
        self._components = components

    async def run(self) -> None:
        await self._components.runner.run()

    def stop(self) -> None:
        self._components.runner.stop()

    async def refresh_configured_connectors(self, force: bool) -> None:
        await self._components.configured_refresher.refresh(force)

    async def refresh_connector(self, connector_id: str) -> None:
        await self._components.connector_refresher.refresh(connector_id)

    def forget_connector(self, connector_id: str) -> None:
        self._components.connector_refresher.forget(connector_id)

    async def initialize_native_capabilities(self) -> None:
        await self._components.native_monitor.initialize()

    async def reconcile_native_capabilities(self) -> None:
        await self._components.native_monitor.reconcile()


def create_downstream_discovery_coordinator(
    stores: DownstreamDiscoveryStores,
    adapters: DownstreamDiscoveryAdapters,
    options: DownstreamDiscoveryCoordinatorOptions,
) -> DownstreamDiscoveryCoordinator:
    schedule = _create_schedule(adapters, options)
    native_monitor = NativeCapabilityChangeMonitor(adapters.native_capabilities, adapters.notifier)
    reconciler = _create_reconciler(stores, native_monitor)
    executor = ConnectorDiscoveryExecutor(
        ConnectorDiscoveryExecutionDependencies(
            definitions=stores.definitions,
            credentials=stores.credentials,
            discovery=adapters.discovery,
        )
    )
    connector_refresher = BoundedConnectorDiscoveryRefresher(
        executor, reconciler, schedule, options.maximum_concurrency
    )
    configured_refresher = ConfiguredConnectorRefresher(
        stores.definitions, connector_refresher, schedule
    )
    runner = PeriodicDiscoveryRunner(options.refresh_interval_seconds, configured_refresher.refresh)
    return DownstreamDiscoveryCoordinator(
        DownstreamDiscoveryComponents(
            runner, configured_refresher, connector_refresher, native_monitor
        )
    )


def _create_schedule(
    adapters: DownstreamDiscoveryAdapters,
    options: DownstreamDiscoveryCoordinatorOptions,
) -> ConnectorDiscoverySchedule:
    return ConnectorDiscoverySchedule(
        ConnectorDiscoveryScheduleOptions(
            options.refresh_interval_seconds,
            options.jitter_ratio,
            options.maximum_backoff_seconds,
        ),
        adapters.monotonic_clock,
        adapters.random_source,
    )


def _create_reconciler(
    stores: DownstreamDiscoveryStores,
    native_monitor: NativeCapabilityChangeMonitor,
) -> DiscoveredCatalogReconciler:
    return DiscoveredCatalogReconciler(
        CatalogReconciliationDependencies(
            stores.catalogs,
            stores.health,
            stores.activations,
            stores.publishing,
            native_monitor,
        )
    )
