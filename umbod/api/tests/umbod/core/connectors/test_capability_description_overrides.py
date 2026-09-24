from umbod.rest.capability_descriptions.base_reader import (
    CompositeConnectorCapabilityBaseDescriptionReader,
)
from umbod.core.capabilities.descriptions.factories import (
    ConfiguredConnectorCapabilityDescriptionOverrideStoreFactory,
)
from umbod.core.capabilities.descriptions.stores.schema import (
    CAPABILITY_DESCRIPTION_OVERRIDE_TABLE,
)
from umbod.core.capabilities.descriptions.stores.service import (
    ConnectorCapabilityDescriptionOverrideStoreService,
)
from tests.persistence_runtime import create_inmemory_runtime, prepared_inmemory_runtime, prepared_sqlite_runtime
import asyncio
import sqlite3
from pathlib import Path
from types import SimpleNamespace
from typing import cast
import pytest
import pytest_asyncio
from pydantic import ValidationError
from umbod.core.capabilities.descriptions import CapabilityDescriptionOverrideResolver, CapabilityDescriptionTargetNotFoundError, ClearCapabilityDescriptionOverride, ConnectorCapabilityDescriptionKey, ConnectorKindMismatchError, ConnectorCapabilityDescriptionOverrideStore, OverrideRevisionConflictError, OverriddenCapabilityDescription, SetCapabilityDescriptionOverride, SystemCapabilityDescription
from umbod.core.connectors.downstream_mcp.models import NoAuthConnectorDefinition
from umbod.core.connectors.downstream_mcp.stores import ConnectorDefinitionFound

@pytest_asyncio.fixture(params=['inmemory', 'sqlite'])
async def store(request: pytest.FixtureRequest, tmp_path: Path) -> ConnectorCapabilityDescriptionOverrideStore:
    if request.param == 'sqlite':
        database = (await prepared_sqlite_runtime(tmp_path / 'umbod.db')).database
        return ConnectorCapabilityDescriptionOverrideStoreService(database, CAPABILITY_DESCRIPTION_OVERRIDE_TABLE)
    database = (await prepared_inmemory_runtime()).database
    return ConnectorCapabilityDescriptionOverrideStoreService(database, CAPABILITY_DESCRIPTION_OVERRIDE_TABLE)

def _key(kind: str='native') -> ConnectorCapabilityDescriptionKey:
    return ConnectorCapabilityDescriptionKey(kind=kind, connector_id='weather')

def _connector_key(kind: str, connector_id: str) -> ConnectorCapabilityDescriptionKey:
    return ConnectorCapabilityDescriptionKey(kind=kind, connector_id=connector_id)

@pytest.mark.asyncio
async def test_missing_override_is_system_revision_zero(store: object) -> None:
    assert await store.get(_key()) == SystemCapabilityDescription(key=_key(), revision=0)

@pytest.mark.asyncio
async def test_set_replace_clear_and_set_after_clear(store: object) -> None:
    first = await store.set(SetCapabilityDescriptionOverride(key=_key(), description=' first ', expected_revision=0))
    assert first == OverriddenCapabilityDescription(key=_key(), description='first', revision=1)
    second = await store.set(SetCapabilityDescriptionOverride(key=_key(), description='second', expected_revision=1))
    assert second.revision == 2
    cleared = await store.clear(ClearCapabilityDescriptionOverride(key=_key(), expected_revision=2))
    assert cleared == SystemCapabilityDescription(key=_key(), revision=3)
    third = await store.set(SetCapabilityDescriptionOverride(key=_key(), description='third', expected_revision=3))
    assert third.revision == 4

@pytest.mark.asyncio
async def test_stale_set_and_clear_are_rejected(store: object) -> None:
    await store.set(SetCapabilityDescriptionOverride(key=_key(), description='first', expected_revision=0))
    with pytest.raises(OverrideRevisionConflictError):
        await store.set(SetCapabilityDescriptionOverride(key=_key(), description='stale', expected_revision=0))
    with pytest.raises(OverrideRevisionConflictError):
        await store.clear(ClearCapabilityDescriptionOverride(key=_key(), expected_revision=0))

@pytest.mark.asyncio
async def test_connector_kind_mismatch_is_rejected(store: object) -> None:
    await store.set(SetCapabilityDescriptionOverride(key=_key(), description='first', expected_revision=0))
    with pytest.raises(ConnectorKindMismatchError):
        await store.get(_key('openapi'))

@pytest.mark.asyncio
async def test_batch_lookup_preserves_missing_and_persisted_states(store: object) -> None:
    await store.set(SetCapabilityDescriptionOverride(key=_key(), description='first', expected_revision=0))
    missing = _connector_key('openapi', 'other')
    assert await store.get_many((_key(), missing)) == (OverriddenCapabilityDescription(key=_key(), description='first', revision=1), SystemCapabilityDescription(key=missing, revision=0))

@pytest.mark.parametrize('description', ['', '   ', 'a' * 301, 'bad\ntext'])
def test_description_validation_boundaries(description: str) -> None:
    with pytest.raises(ValidationError):
        SetCapabilityDescriptionOverride(key=_key(), description=description, expected_revision=0)

def test_description_accepts_300_characters() -> None:
    command = SetCapabilityDescriptionOverride(key=_key(), description='a' * 300, expected_revision=0)
    assert len(command.description) == 300

@pytest.mark.asyncio
async def test_configured_factory_returns_one_store_during_concurrent_initialization(tmp_path: Path) -> None:
    factory = ConfiguredConnectorCapabilityDescriptionOverrideStoreFactory(create_inmemory_runtime().database)
    (first, second) = await asyncio.gather(factory.create(), factory.create())
    assert first is second

@pytest.mark.asyncio
async def test_sqlite_two_connection_compare_and_swap(tmp_path: Path) -> None:
    path = tmp_path / 'umbod.db'
    database = (await prepared_sqlite_runtime(path)).database
    first = ConnectorCapabilityDescriptionOverrideStoreService(database, CAPABILITY_DESCRIPTION_OVERRIDE_TABLE)
    second = ConnectorCapabilityDescriptionOverrideStoreService(database, CAPABILITY_DESCRIPTION_OVERRIDE_TABLE)
    await first.set(SetCapabilityDescriptionOverride(key=_key(), description='first', expected_revision=0))
    with pytest.raises(OverrideRevisionConflictError):
        await second.set(SetCapabilityDescriptionOverride(key=_key(), description='second', expected_revision=0))

@pytest.mark.asyncio
async def test_sqlite_schema_has_state_constraints_and_initializes_idempotently(tmp_path: Path) -> None:
    path = tmp_path / 'umbod.db'
    runtime = await prepared_sqlite_runtime(path)
    await runtime.readiness.ensure_ready()
    with sqlite3.connect(path) as connection:
        sql = connection.execute("SELECT sql FROM sqlite_master WHERE name = 'connector_capability_description_overrides'").fetchone()[0]
        assert 'CHECK' in sql
        assert connection.execute('SELECT count(*) FROM connector_capability_description_overrides').fetchone()[0] == 0

class _BaseReader:

    async def read(self, key: ConnectorCapabilityDescriptionKey) -> str:
        return 'system description'

class _NativeRegistry:

    def get_connector_definition(self, connector_id: str, filters: object) -> object:
        if connector_id != 'native-id':
            return None
        return SimpleNamespace(metadata=SimpleNamespace(capability_description='native base'))

class _DownstreamStore:

    async def get(self, query: object) -> ConnectorDefinitionFound:
        definition = NoAuthConnectorDefinition(connector_id='downstream-id', display_name='Downstream', capability_description='downstream base', endpoint_url='https://example.com/mcp', public_path='/mcp/proxies/downstream-id')
        return ConnectorDefinitionFound(definition=definition)

class _OpenApiReader:

    async def get_connector(self, connector_id: str) -> object:
        if connector_id != 'openapi-id':
            raise KeyError(connector_id)
        return SimpleNamespace(capability_description='openapi base')

@pytest.mark.asyncio
async def test_composite_base_reader_reads_all_connector_kinds() -> None:
    reader = CompositeConnectorCapabilityBaseDescriptionReader(cast(object, _NativeRegistry()), cast(object, _DownstreamStore()), cast(object, _OpenApiReader()))
    assert await reader.read(_connector_key('native', 'native-id')) == 'native base'
    assert await reader.read(_connector_key('downstream_mcp', 'downstream-id')) == 'downstream base'
    assert await reader.read(_connector_key('openapi', 'openapi-id')) == 'openapi base'

@pytest.mark.asyncio
async def test_composite_base_reader_rejects_missing_target() -> None:
    reader = CompositeConnectorCapabilityBaseDescriptionReader(cast(object, _NativeRegistry()), cast(object, _DownstreamStore()), cast(object, _OpenApiReader()))
    with pytest.raises(CapabilityDescriptionTargetNotFoundError):
        await reader.read(_connector_key('native', 'missing'))

@pytest.mark.asyncio
async def test_resolver_returns_base_for_system_and_override_when_set() -> None:
    database = (await prepared_inmemory_runtime()).database
    store = ConnectorCapabilityDescriptionOverrideStoreService(database, CAPABILITY_DESCRIPTION_OVERRIDE_TABLE)
    resolver = CapabilityDescriptionOverrideResolver(store, _BaseReader())
    assert (await resolver.resolve(_key())).description == 'system description'
    await store.set(SetCapabilityDescriptionOverride(key=_key(), description='custom', expected_revision=0))
    assert (await resolver.resolve(_key())).description == 'custom'
