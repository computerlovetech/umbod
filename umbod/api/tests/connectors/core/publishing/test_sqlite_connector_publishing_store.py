from umbod.core.publishing.factories import create_connector_publishing_store
from collections.abc import Awaitable, Callable
from pathlib import Path
import sqlite3

import pytest

from umbod.core.publishing import (
    ConnectorPublishingStore,
    ConnectorPublishStateChanged,
    ConnectorPublishStateChangeSource,
)
from tests.persistence_runtime import prepared_inmemory_runtime, prepared_sqlite_runtime

PublishingStoreFactory = Callable[[Path], Awaitable[ConnectorPublishingStore]]


async def _in_memory_publishing_store(_tmp_path: Path) -> ConnectorPublishingStore:
    database = (await prepared_inmemory_runtime()).database
    return await create_connector_publishing_store(database)


async def _sqlite_publishing_store(tmp_path: Path) -> ConnectorPublishingStore:
    database = (await prepared_sqlite_runtime(tmp_path / 'connectors.sqlite')).database
    return await create_connector_publishing_store(database)


@pytest.fixture(params=[_in_memory_publishing_store, _sqlite_publishing_store])
def publishing_store_factory(request: pytest.FixtureRequest) -> PublishingStoreFactory:
    return request.param


@pytest.mark.asyncio
async def test_publish_marks_connector_published_and_previously_published(
    publishing_store_factory: PublishingStoreFactory, tmp_path: Path
) -> None:
    store = await publishing_store_factory(tmp_path)
    await store.publish_connector('slack')
    assert await store.is_published('slack') is True
    assert await store.was_previously_published('slack') is True


@pytest.mark.asyncio
async def test_unpublish_marks_published_connector_unpublished_and_previously_published(
    publishing_store_factory: PublishingStoreFactory, tmp_path: Path
) -> None:
    store = await publishing_store_factory(tmp_path)
    await store.publish_connector('slack')
    await store.unpublish_connector('slack')
    assert await store.is_published('slack') is False
    assert await store.was_previously_published('slack') is True


@pytest.mark.asyncio
async def test_missing_connector_is_unpublished_and_not_previously_published(
    publishing_store_factory: PublishingStoreFactory, tmp_path: Path
) -> None:
    store = await publishing_store_factory(tmp_path)
    await store.unpublish_connector('missing')
    assert await store.is_published('missing') is False
    assert await store.was_previously_published('missing') is False


@pytest.mark.asyncio
async def test_same_process_subscribers_receive_publish_state_changes(
    publishing_store_factory: PublishingStoreFactory, tmp_path: Path
) -> None:
    store = await publishing_store_factory(tmp_path)
    received_events: list[ConnectorPublishStateChanged] = []
    assert isinstance(store, ConnectorPublishStateChangeSource)

    async def _record(event: ConnectorPublishStateChanged) -> None:
        received_events.append(event)

    store.subscribe_publish_state_changes(_record)
    await store.publish_connector('slack')
    await store.unpublish_connector('slack')
    assert received_events == [
        ConnectorPublishStateChanged(connector_id='slack', state='published'),
        ConnectorPublishStateChanged(connector_id='slack', state='unpublished'),
    ]


@pytest.mark.asyncio
async def test_sqlite_store_instances_share_persisted_publication_state(tmp_path: Path) -> None:
    database_path = str(tmp_path / 'connectors.sqlite')
    database = (await prepared_sqlite_runtime(database_path)).database
    writer = await create_connector_publishing_store(database)
    reader = await create_connector_publishing_store(database)
    await writer.publish_connector('slack')
    assert await reader.is_published('slack') is True
    assert await reader.was_previously_published('slack') is True
    await writer.unpublish_connector('slack')
    assert await reader.is_published('slack') is False
    assert await reader.was_previously_published('slack') is True


@pytest.mark.asyncio
async def test_sqlite_publication_revision_progresses_across_restart(tmp_path: Path) -> None:
    database_path = str(tmp_path / 'connectors.sqlite')
    database = (await prepared_sqlite_runtime(database_path)).database
    store = await create_connector_publishing_store(database)
    await store.publish_connector('slack')
    await store.publish_connector('slack')
    await store.unpublish_connector('slack')
    restarted_store = await create_connector_publishing_store(database)
    await restarted_store.publish_connector('slack')
    with sqlite3.connect(database_path) as connection:
        row = connection.execute(
            'SELECT published, previously_published, revision, updated_at FROM connector_publication_states WHERE connector_id = ?',
            ('slack',),
        ).fetchone()
    assert row is not None
    assert row[0:3] == (1, 1, 4)
    assert isinstance(row[3], str)
    assert row[3]
