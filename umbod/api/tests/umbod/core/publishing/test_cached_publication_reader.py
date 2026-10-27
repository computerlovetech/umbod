from unittest.mock import AsyncMock, call
from uuid import UUID

import pytest

from umbod.core.caching import AsyncRequestCache
from umbod.core.publishing.cached import CachedConnectorPublicationReader
from umbod.core.publishing.store import ConnectorPublicationReader
from umbod.infrastructure import create_request_cache


@pytest.mark.asyncio
async def test_operation_and_connector_keys_cache_false_independently() -> None:
    source = AsyncMock(spec=ConnectorPublicationReader)
    source.is_published.side_effect = [False, True]
    source.was_previously_published.side_effect = [True, False]
    underlying: ConnectorPublicationReader = source
    cache: AsyncRequestCache[tuple[UUID, str, str], bool] = create_request_cache()
    reader: ConnectorPublicationReader = CachedConnectorPublicationReader(underlying, cache)

    for _ in range(2):
        assert await reader.is_published("first") is False
        assert await reader.is_published("second") is True
        assert await reader.was_previously_published("first") is True
        assert await reader.was_previously_published("second") is False

    assert source.is_published.await_args_list == [call("first"), call("second")]
    assert source.was_previously_published.await_args_list == [call("first"), call("second")]


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["is_published", "was_previously_published"])
async def test_failed_read_propagates_and_retries(operation: str) -> None:
    source = AsyncMock(spec=ConnectorPublicationReader)
    method = getattr(source, operation)
    method.side_effect = [RuntimeError("unavailable"), False]
    underlying: ConnectorPublicationReader = source
    cache: AsyncRequestCache[tuple[UUID, str, str], bool] = create_request_cache()
    reader: ConnectorPublicationReader = CachedConnectorPublicationReader(underlying, cache)
    read = getattr(reader, operation)

    with pytest.raises(RuntimeError, match="unavailable"):
        await read("connector")
    assert await read("connector") is False
    assert await read("connector") is False
    assert method.await_count == 2


@pytest.mark.asyncio
async def test_wrappers_are_isolated_even_with_shared_typed_cache() -> None:
    source = AsyncMock(spec=ConnectorPublicationReader)
    source.is_published.side_effect = [False, True]
    source.was_previously_published.side_effect = [True, False]
    underlying: ConnectorPublicationReader = source
    cache: AsyncRequestCache[tuple[UUID, str, str], bool] = create_request_cache()
    first: ConnectorPublicationReader = CachedConnectorPublicationReader(underlying, cache)
    second: ConnectorPublicationReader = CachedConnectorPublicationReader(underlying, cache)

    for _ in range(2):
        assert await first.is_published("connector") is False
        assert await second.is_published("connector") is True
        assert await first.was_previously_published("connector") is True
        assert await second.was_previously_published("connector") is False

    assert source.is_published.await_count == 2
    assert source.was_previously_published.await_count == 2


@pytest.mark.asyncio
async def test_fresh_request_cache_reads_current_publication_state() -> None:
    source = AsyncMock(spec=ConnectorPublicationReader)
    source.is_published.side_effect = [False, True]
    source.was_previously_published.side_effect = [False, True]
    underlying: ConnectorPublicationReader = source

    for expected in (False, True):
        cache: AsyncRequestCache[tuple[UUID, str, str], bool] = create_request_cache()
        reader: ConnectorPublicationReader = CachedConnectorPublicationReader(underlying, cache)
        for _ in range(2):
            assert await reader.is_published("connector") is expected
            assert await reader.was_previously_published("connector") is expected

    assert source.is_published.await_count == 2
    assert source.was_previously_published.await_count == 2
