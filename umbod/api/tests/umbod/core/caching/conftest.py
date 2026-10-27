import pytest

from umbod.core.caching import AsyncRequestCache
from umbod.infrastructure import create_request_cache


@pytest.fixture
def cache() -> AsyncRequestCache[str, object]:
    return create_request_cache()
