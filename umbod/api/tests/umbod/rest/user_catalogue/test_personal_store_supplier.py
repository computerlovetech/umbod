import asyncio
from pathlib import Path

import pytest

from tests.persistence_runtime import prepared_inmemory_runtime, prepared_sqlite_runtime
from umbod.core.connectors.downstream_mcp.stores import DownstreamMcpStores, create_downstream_mcp_stores
from umbod.core.connectors.downstream_mcp.adapters.settings import DownstreamMcpInfrastructureSettings
from umbod.core.connectors.downstream_mcp.stores import ConnectorIdQuery, SaveConnectorDefinition
from umbod.core.connectors.downstream_mcp.models import NoAuthConnectorDefinition
from umbod.core.persistence import Database, PersistenceReadiness, PersistenceRuntime
from umbod.rest.factories import ConnectorApiDependencyFactories
from umbod.rest.settings import APISettings
from umbod.rest.user_catalogue.ports import PersonalCatalogueStoreSupplier
from umbod.rest.user_catalogue.store_supplier import ConfiguredPersonalCatalogueStoreSupplier
from umbod.rest.user_catalogue import store_supplier


@pytest.mark.asyncio
async def test_cancellation_during_readiness_leaves_runtime_with_application() -> None:
    runtime = await prepared_inmemory_runtime()
    events: list[str] = []
    readiness = BlockingReadiness(events)
    recording_runtime = RecordingRuntime(runtime, events, readiness)
    supplier: PersonalCatalogueStoreSupplier = ConfiguredPersonalCatalogueStoreSupplier(APISettings(), recording_runtime)
    task = asyncio.create_task(supplier.create())
    try:
        await asyncio.wait_for(readiness.started.wait(), timeout=1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, timeout=1)
        assert events == ["readiness"]
        stores = await create_downstream_mcp_stores("test-secret", runtime.database)
        await stores.publishing.publish_connector("after-cancellation")
        assert await stores.publishing.is_published("after-cancellation")
    finally:
        task.cancel()
        await asyncio.wait_for(asyncio.gather(task, return_exceptions=True), timeout=5)
        await runtime.shutdown()


class FixedPersonalCatalogueStoreSupplier:
    def __init__(self, stores: DownstreamMcpStores) -> None:
        self.stores = stores
        self.calls = 0

    async def create(self) -> DownstreamMcpStores:
        self.calls += 1
        return self.stores


@pytest.mark.asyncio
async def test_fixed_supplier_returns_existing_validated_bundle() -> None:
    runtime = await prepared_inmemory_runtime()
    try:
        stores = await create_downstream_mcp_stores("test-secret", runtime.database)
        fixed = FixedPersonalCatalogueStoreSupplier(stores)
        supplier: PersonalCatalogueStoreSupplier = fixed
        assert await supplier.create() is stores
        assert fixed.calls == 1
    finally:
        await runtime.shutdown()


@pytest.mark.asyncio
@pytest.mark.parametrize("backend", ["inmemory", "sqlite"])
async def test_composed_supplier_returns_fresh_stores_over_application_database(
    tmp_path: Path, backend: str,
) -> None:
    runtime = (
        await prepared_inmemory_runtime()
        if backend == "inmemory" else await prepared_sqlite_runtime(tmp_path / "supplier.sqlite")
    )
    try:
        factories = ConnectorApiDependencyFactories.from_settings(APISettings(), runtime, [])
        supplier: PersonalCatalogueStoreSupplier = factories.personal_catalogue_stores
        first = await supplier.create()
        second = await supplier.create()
        assert first is not second
        assert first.personal_connections is not second.personal_connections
        definition = NoAuthConnectorDefinition(
            connector_id="shared-database", display_name="Shared database", tool_name_prefix="SharedDatabase",
            endpoint_url="https://example.invalid/mcp",
        )
        await first.definitions.save(SaveConnectorDefinition(definition=definition))
        query = ConnectorIdQuery(connector_id=definition.connector_id)
        assert (await second.definitions.get(query)).definition == definition
        assert (await factories.downstream_mcp_definition_store.create().get(query)).definition == definition
    finally:
        await runtime.shutdown()


class RecordingReadiness:
    def __init__(self, events: list[str], stage: str, failure: BaseException) -> None:
        self.events = events
        self.stage = stage
        self.failure = failure

    async def ensure_ready(self) -> None:
        self.events.append("readiness")
        if self.stage == "readiness":
            raise self.failure


class BlockingReadiness:
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    async def ensure_ready(self) -> None:
        self.events.append("readiness")
        self.started.set()
        await asyncio.wait_for(self.release.wait(), timeout=30)


class RecordingRuntime:
    def __init__(self, runtime: PersistenceRuntime, events: list[str], readiness: PersistenceReadiness) -> None:
        self.runtime = runtime
        self.events = events
        self.recording_readiness = readiness

    @property
    def database(self) -> Database:
        self.events.append("database")
        return self.runtime.database

    @property
    def readiness(self) -> PersistenceReadiness:
        return self.recording_readiness

    async def shutdown(self) -> None:
        self.events.append("shutdown")


@pytest.mark.asyncio
@pytest.mark.parametrize("stage", ["settings", "readiness", "construction", "cancellation"])
async def test_supplier_defers_work_and_propagates_failures_without_retry_or_shutdown(
    monkeypatch: pytest.MonkeyPatch, stage: str,
) -> None:
    runtime = await prepared_inmemory_runtime()
    events: list[str] = []
    failure = asyncio.CancelledError(stage) if stage == "cancellation" else RuntimeError(stage)
    recording_runtime = RecordingRuntime(runtime, events, RecordingReadiness(events, stage, failure))

    def settings_from_config(settings: APISettings) -> DownstreamMcpInfrastructureSettings:
        events.append("settings")
        if stage == "settings":
            raise failure
        return DownstreamMcpInfrastructureSettings(
            credential_secret="test-secret", tls_verification=True,
            connection_timeout_seconds=10.0, discovery_timeout_seconds=10.0, oauth_enabled=False,
        )

    async def construct_stores(secret: str, database: Database) -> DownstreamMcpStores:
        events.append("construction")
        assert secret == "test-secret"
        assert database is runtime.database
        raise failure

    monkeypatch.setattr(store_supplier, "downstream_mcp_infrastructure_settings_from_app_config", settings_from_config)
    monkeypatch.setattr(store_supplier, "create_downstream_mcp_stores", construct_stores)
    supplier: PersonalCatalogueStoreSupplier = ConfiguredPersonalCatalogueStoreSupplier(APISettings(), recording_runtime)
    assert events == []
    try:
        with pytest.raises(type(failure)) as caught:
            await supplier.create()
        assert caught.value is failure
        expected = ["settings"] if stage == "settings" else ["settings", "readiness"] if stage == "readiness" else [
            "settings", "readiness", "database", "construction",
        ]
        assert events == expected
        stores = await create_downstream_mcp_stores("test-secret", runtime.database)
        await stores.publishing.publish_connector("still-owned-by-app")
        assert await stores.publishing.is_published("still-owned-by-app")
    finally:
        await runtime.shutdown()
