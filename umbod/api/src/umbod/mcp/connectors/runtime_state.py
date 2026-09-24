import asyncio
import json
from typing import Any, Protocol
from urllib.error import HTTPError
from urllib.request import urlopen

from pydantic import SecretStr, TypeAdapter
from umbod.mcp.proxies import Model

from umbod.core.configuration import ConnectorCurrentConfigurationStore
from umbod.core.publishing import ConnectorPublishingStore
from umbod.core.connectors.native.registry import ConnectorDefinitionFilter, ConnectorRegistry


class ConnectorRuntimeState(Model):
    connector_id: str
    display_name: str | None = None
    available: bool
    published: bool
    configuration: dict[str, object] | None = None


class ConnectorRuntimeStateReader(Protocol):
    async def get_connector_runtime_state(
        self, connector_id: str
    ) -> ConnectorRuntimeState | None: ...

    async def list_connector_runtime_states(self) -> list[ConnectorRuntimeState]: ...


class StoreBackedConnectorRuntimeStateReader:
    def __init__(
        self,
        connector_registry: ConnectorRegistry,
        configuration_store: ConnectorCurrentConfigurationStore,
        publishing_store: ConnectorPublishingStore,
    ) -> None:
        self._connector_registry = connector_registry
        self._configuration_store = configuration_store
        self._publishing_store = publishing_store

    async def get_connector_runtime_state(
        self, connector_id: str
    ) -> ConnectorRuntimeState | None:
        definition = self._connector_registry.get_connector_definition(
            connector_id,
            ConnectorDefinitionFilter(availability="registered"),
        )
        if definition is None:
            return None
        configuration = await self._configuration_store.get_current_configuration(connector_id)
        serialized_configuration = (
            None if configuration is None else self._dump_configuration(configuration)
        )
        return ConnectorRuntimeState(
            connector_id=connector_id,
            display_name=definition.metadata.display_name,
            available=definition.available,
            published=await self._publishing_store.is_published(connector_id),
            configuration=serialized_configuration,
        )

    async def list_connector_runtime_states(self) -> list[ConnectorRuntimeState]:
        definitions = self._connector_registry.list_connector_definitions(
            ConnectorDefinitionFilter(availability="registered")
        )
        states: list[ConnectorRuntimeState] = []
        for definition in definitions:
            state = await self.get_connector_runtime_state(definition.metadata.id)
            if state is not None:
                states.append(state)
        return states

    def _dump_configuration(self, configuration: Model) -> dict[str, object]:
        return {
            key: self._reveal_secret(value)
            for key, value in configuration.model_dump().items()
        }

    def _reveal_secret(self, value: Any) -> object:
        if isinstance(value, SecretStr):
            return value.get_secret_value()
        if isinstance(value, dict):
            return {str(key): self._reveal_secret(item) for key, item in value.items()}
        if isinstance(value, list):
            return [self._reveal_secret(item) for item in value]
        return value


SQLiteConnectorRuntimeStateReader = StoreBackedConnectorRuntimeStateReader


class RuntimeConnectorToolReconciler(Protocol):
    def configuration_schema_for_connector(self, connector_id: str) -> type[Model] | None: ...

    async def reconcile_connector(self, connector_id: str) -> None: ...

    async def reconcile_all(self) -> None: ...


class HttpConnectorRuntimeStateReader:
    def __init__(self, api_base_url: str) -> None:
        self._api_base_url = api_base_url.rstrip("/")
        self._state_adapter = TypeAdapter(ConnectorRuntimeState)
        self._states_adapter = TypeAdapter(list[ConnectorRuntimeState])

    async def get_connector_runtime_state(self, connector_id: str) -> ConnectorRuntimeState | None:
        return await asyncio.to_thread(self._get_connector_runtime_state_sync, connector_id)

    async def list_connector_runtime_states(self) -> list[ConnectorRuntimeState]:
        return await asyncio.to_thread(self._list_connector_runtime_states_sync)

    def _get_connector_runtime_state_sync(self, connector_id: str) -> ConnectorRuntimeState | None:
        url = f"{self._api_base_url}/system/connectors/{connector_id}/runtime-state"
        try:
            with urlopen(url, timeout=10) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except HTTPError as error:
            if error.code == 404:
                return None
            raise
        return self._state_adapter.validate_python(payload)

    def _list_connector_runtime_states_sync(self) -> list[ConnectorRuntimeState]:
        url = f"{self._api_base_url}/system/connectors/runtime-state"
        with urlopen(url, timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8"))
        return self._states_adapter.validate_python(payload)


class ConnectorRuntimeStateSink(Protocol):
    async def apply_runtime_state(self, state: ConnectorRuntimeState) -> None: ...

    async def apply_connector_store_state(
        self,
        connector_id: str,
        configuration_store: ConnectorCurrentConfigurationStore,
        publishing_store: ConnectorPublishingStore,
    ) -> None: ...


class ConnectorRuntimeStateSynchronizationSource(Protocol):
    async def synchronize(self, connector_id: str, sink: ConnectorRuntimeStateSink) -> bool: ...

    async def synchronize_all(
        self, reader: ConnectorRuntimeStateReader, sink: ConnectorRuntimeStateSink
    ) -> None: ...


class HttpConnectorRuntimeStateSynchronizationSource:
    def __init__(self, reader: ConnectorRuntimeStateReader) -> None:
        self._reader = reader

    async def synchronize(self, connector_id: str, sink: ConnectorRuntimeStateSink) -> bool:
        state = await self._reader.get_connector_runtime_state(connector_id)
        if state is None:
            return False
        await sink.apply_runtime_state(state)
        return True

    async def synchronize_all(
        self, reader: ConnectorRuntimeStateReader, sink: ConnectorRuntimeStateSink
    ) -> None:
        for state in await reader.list_connector_runtime_states():
            await sink.apply_runtime_state(state)


class StoreBackedConnectorRuntimeStateSynchronizationSource:
    def __init__(self, reader: ConnectorRuntimeStateReader) -> None:
        self._reader = reader

    async def synchronize(self, connector_id: str, sink: ConnectorRuntimeStateSink) -> bool:
        return await self._reader.get_connector_runtime_state(connector_id) is not None

    async def synchronize_all(
        self, reader: ConnectorRuntimeStateReader, sink: ConnectorRuntimeStateSink
    ) -> None:
        await reader.list_connector_runtime_states()


class LocalConnectorRuntimeStateSynchronizationSource:
    def __init__(
        self,
        configuration_store: ConnectorCurrentConfigurationStore,
        publishing_store: ConnectorPublishingStore,
    ) -> None:
        self._configuration_store = configuration_store
        self._publishing_store = publishing_store

    async def synchronize(self, connector_id: str, sink: ConnectorRuntimeStateSink) -> bool:
        await sink.apply_connector_store_state(
            connector_id,
            self._configuration_store,
            self._publishing_store,
        )
        return True

    async def synchronize_all(
        self, reader: ConnectorRuntimeStateReader, sink: ConnectorRuntimeStateSink
    ) -> None:
        for state in await reader.list_connector_runtime_states():
            await sink.apply_runtime_state(state)


class ConnectorRuntimeStateSynchronizer:
    def __init__(
        self,
        *,
        reader: ConnectorRuntimeStateReader,
        configuration_store: ConnectorCurrentConfigurationStore,
        publishing_store: ConnectorPublishingStore,
        tool_registry: RuntimeConnectorToolReconciler,
        synchronization_source: ConnectorRuntimeStateSynchronizationSource,
    ) -> None:
        self._reader = reader
        self._configuration_store = configuration_store
        self._publishing_store = publishing_store
        self._tool_registry = tool_registry
        self._synchronization_source = synchronization_source

    async def sync_connector(self, connector_id: str) -> None:
        synchronized = await self._synchronization_source.synchronize(connector_id, self)
        if synchronized:
            await self._tool_registry.reconcile_connector(connector_id)

    async def sync_all(self) -> None:
        await self._synchronization_source.synchronize_all(self._reader, self)
        await self._tool_registry.reconcile_all()

    async def apply_runtime_state(self, state: ConnectorRuntimeState) -> None:
        await self._sync_configuration(state)
        await self._sync_publication(state)

    async def apply_connector_store_state(
        self,
        connector_id: str,
        configuration_store: ConnectorCurrentConfigurationStore,
        publishing_store: ConnectorPublishingStore,
    ) -> None:
        await self._sync_configuration_from_store(connector_id, configuration_store)
        await self._sync_publication_from_store(connector_id, publishing_store)

    async def _sync_configuration_from_store(
        self,
        connector_id: str,
        source_configuration_store: ConnectorCurrentConfigurationStore,
    ) -> None:
        schema = self._tool_registry.configuration_schema_for_connector(connector_id)
        if schema is None:
            return
        configuration = await source_configuration_store.get_current_configuration(connector_id)
        if configuration is None:
            await self._configuration_store.delete_current_configuration(connector_id)
            return
        await self._configuration_store.save_current_configuration(
            connector_id,
            schema.model_validate(configuration),
        )

    async def _sync_publication_from_store(
        self,
        connector_id: str,
        source_publishing_store: ConnectorPublishingStore,
    ) -> None:
        if await source_publishing_store.is_published(connector_id):
            await self._publishing_store.publish_connector(connector_id)
        else:
            await self._publishing_store.unpublish_connector(connector_id)

    async def _sync_configuration(self, state: ConnectorRuntimeState) -> None:
        schema = self._tool_registry.configuration_schema_for_connector(state.connector_id)
        if schema is None:
            return
        if state.configuration is None:
            await self._configuration_store.delete_current_configuration(state.connector_id)
            return
        await self._configuration_store.save_current_configuration(
            state.connector_id,
            schema.model_validate(state.configuration),
        )

    async def _sync_publication(self, state: ConnectorRuntimeState) -> None:
        if state.published:
            await self._publishing_store.publish_connector(state.connector_id)
        else:
            await self._publishing_store.unpublish_connector(state.connector_id)
