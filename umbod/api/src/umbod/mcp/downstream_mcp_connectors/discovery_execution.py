import asyncio
import logging
from dataclasses import dataclass

from umbod.core.connectors.downstream_mcp.models import (
    DiscoveryFailed,
    DiscoveryResult,
    DiscoverySucceeded,
)
from umbod.core.connectors.downstream_mcp.stores import (
    ConnectorDefinitionFound,
    ConnectorDefinitionStore,
    ConnectorIdQuery,
    CredentialFound,
    EncryptedCredentialStore,
)
from umbod.core.connectors.downstream_mcp.probe import (
    DiscoverDownstreamTools,
    DownstreamDiscovery,
)
from umbod.mcp.downstream_mcp_connectors.catalog_reconciliation import (
    DiscoveredCatalogReconciler,
)
from umbod.mcp.downstream_mcp_connectors.discovery_scheduling import (
    ConnectorDiscoverySchedule,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ConnectorDiscoveryExecutionDependencies:
    definitions: ConnectorDefinitionStore
    credentials: EncryptedCredentialStore
    discovery: DownstreamDiscovery


class ConnectorDiscoveryExecutor:
    def __init__(self, dependencies: ConnectorDiscoveryExecutionDependencies) -> None:
        self._dependencies = dependencies

    async def execute(self, connector_id: str) -> DiscoveryResult | None:
        query = ConnectorIdQuery(connector_id=connector_id)
        definition = await self._dependencies.definitions.get(query)
        credential = await self._dependencies.credentials.get(query)
        if not isinstance(definition, ConnectorDefinitionFound) or not isinstance(
            credential, CredentialFound
        ):
            return None
        return await self._dependencies.discovery.discover(
            DiscoverDownstreamTools(
                definition=definition.definition,
                credential=credential.credential,
            )
        )


@dataclass
class BoundedConnectorDiscoveryState:
    executor: ConnectorDiscoveryExecutor
    reconciler: DiscoveredCatalogReconciler
    schedule: ConnectorDiscoverySchedule
    semaphore: asyncio.Semaphore
    locks: dict[str, asyncio.Lock]


class BoundedConnectorDiscoveryRefresher:
    def __init__(
        self,
        executor: ConnectorDiscoveryExecutor,
        reconciler: DiscoveredCatalogReconciler,
        schedule: ConnectorDiscoverySchedule,
        maximum_concurrency: int,
    ) -> None:
        self._state = BoundedConnectorDiscoveryState(
            executor=executor,
            reconciler=reconciler,
            schedule=schedule,
            semaphore=asyncio.Semaphore(maximum_concurrency),
            locks={},
        )

    async def refresh(self, connector_id: str) -> None:
        lock = self._state.locks.setdefault(connector_id, asyncio.Lock())
        if lock.locked():
            return
        async with lock, self._state.semaphore:
            result = await self._state.executor.execute(connector_id)
            if isinstance(result, DiscoveryFailed):
                await self._state.reconciler.record_failure(result)
                failures = self._state.schedule.record_failure(connector_id)
                logger.warning(
                    "Downstream MCP discovery failed",
                    extra={"connector_id": connector_id, "failure_count": failures},
                )
                return
            if isinstance(result, DiscoverySucceeded):
                await self._state.reconciler.reconcile(result)
                self._state.schedule.record_success(connector_id)

    def forget(self, connector_id: str) -> None:
        lock = self._state.locks.get(connector_id)
        if lock is not None and lock.locked():
            return
        self._state.locks.pop(connector_id, None)
        self._state.schedule.forget(connector_id)

    def connector_ids(self) -> set[str]:
        return set(self._state.locks)


class ConfiguredConnectorRefresher:
    def __init__(
        self,
        definitions: ConnectorDefinitionStore,
        connector_refresher: BoundedConnectorDiscoveryRefresher,
        schedule: ConnectorDiscoverySchedule,
    ) -> None:
        self._definitions = definitions
        self._connector_refresher = connector_refresher
        self._schedule = schedule

    async def refresh(self, force: bool) -> None:
        connector_ids = tuple(
            definition.connector_id for definition in (await self._definitions.list()).definitions
        )
        current_connector_ids = set(connector_ids)
        for stale_connector_id in self._connector_refresher.connector_ids() - current_connector_ids:
            self._connector_refresher.forget(stale_connector_id)
        now = self._schedule.now()
        await asyncio.gather(
            *(
                self._connector_refresher.refresh(connector_id)
                for connector_id in connector_ids
                if force or self._schedule.is_due(connector_id, now)
            )
        )
