from umbod.core.publishing.factories import create_connector_publishing_store
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio

from umbod.core.publishing import (
    ConnectorPublishingStore,
    ConnectorPublishStateChanged,
    ConnectorPublishStateChangeSource,
)
from tests.persistence_runtime import prepared_inmemory_runtime
from umbod.core.persistence import Database, Equals, Query, Unordered
from umbod.core.publishing.stores.schema import (
    PUBLICATION_STATE_CONNECTOR_ID,
    PUBLICATION_STATE_PROJECTION,
    PUBLICATION_STATE_TABLE,
)


@pytest_asyncio.fixture
async def database() -> AsyncIterator[Database]:
    runtime = await prepared_inmemory_runtime()
    try:
        yield runtime.database
    finally:
        await runtime.shutdown()


@pytest_asyncio.fixture
async def store(database: Database) -> ConnectorPublishingStore:
    return await create_connector_publishing_store(database)


@pytest.mark.asyncio
async def test_publish_marks_connector_published_and_previously_published(store: ConnectorPublishingStore) -> None:
    await store.publish_connector('slack')
    assert await store.is_published('slack') is True
    assert await store.was_previously_published('slack') is True


@pytest.mark.asyncio
async def test_unpublish_marks_published_connector_unpublished_and_previously_published(store: ConnectorPublishingStore) -> None:
    await store.publish_connector('slack')
    await store.unpublish_connector('slack')
    assert await store.is_published('slack') is False
    assert await store.was_previously_published('slack') is True


@pytest.mark.asyncio
async def test_missing_connector_is_unpublished_and_not_previously_published(store: ConnectorPublishingStore) -> None:
    await store.unpublish_connector('missing')
    assert await store.is_published('missing') is False
    assert await store.was_previously_published('missing') is False


@pytest.mark.asyncio
async def test_same_process_subscribers_receive_publish_state_changes(store: ConnectorPublishingStore) -> None:
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
async def test_store_instances_share_publication_state(database: Database) -> None:
    writer = await create_connector_publishing_store(database)
    reader = await create_connector_publishing_store(database)
    await writer.publish_connector('slack')
    assert await reader.is_published('slack') is True
    assert await reader.was_previously_published('slack') is True
    await writer.unpublish_connector('slack')
    assert await reader.is_published('slack') is False
    assert await reader.was_previously_published('slack') is True


@pytest.mark.asyncio
async def test_publication_revision_progresses_across_store_recreation(database: Database) -> None:
    store = await create_connector_publishing_store(database)
    await store.publish_connector('slack')
    await store.publish_connector('slack')
    await store.unpublish_connector('slack')
    recreated_store = await create_connector_publishing_store(database)
    await recreated_store.publish_connector('slack')
    async with database.read_session() as session:
        row = await session.find_one(
            PUBLICATION_STATE_TABLE,
            Query(
                Equals(PUBLICATION_STATE_CONNECTOR_ID, 'slack'),
                PUBLICATION_STATE_PROJECTION,
                Unordered(),
            ),
        )
    assert row is not None
    assert (row.published, row.previously_published, row.revision) == (True, True, 4)
    assert isinstance(row.updated_at, str)
    assert row.updated_at
