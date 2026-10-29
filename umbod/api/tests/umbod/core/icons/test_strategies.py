import pytest

from umbod.core.icons import (
    AdvertisedIconStrategy,
    Favicon,
    FaviconDiscoveryRequest,
    FaviconDiscoveryStrategy,
    FaviconFound,
    FaviconNotFound,
)
from tests.support.icons import InMemoryFaviconDiscoveryStrategy


@pytest.mark.asyncio
async def test_advertised_strategy_returns_first_icon(
    discovery_request: FaviconDiscoveryRequest, found: FaviconFound
) -> None:
    strategy: FaviconDiscoveryStrategy = AdvertisedIconStrategy()
    incoming = discovery_request.model_copy(
        update={
            "advertised_icons": (
                found.icon,
                Favicon(url="data:image/png;base64,YQ==", mime_type="image/png"),
            )
        }
    )

    assert await strategy.discover(incoming) == FaviconFound(
        icon=found.icon, strategy="advertised"
    )


@pytest.mark.asyncio
async def test_advertised_strategy_without_icons_returns_miss(
    discovery_request: FaviconDiscoveryRequest,
) -> None:
    strategy: FaviconDiscoveryStrategy = AdvertisedIconStrategy()

    assert await strategy.discover(discovery_request) == FaviconNotFound()


@pytest.mark.parametrize("known", [True, False])
@pytest.mark.asyncio
async def test_in_memory_strategy_uses_endpoint_mapping(
    discovery_request: FaviconDiscoveryRequest, found: FaviconFound, known: bool
) -> None:
    strategy: FaviconDiscoveryStrategy = InMemoryFaviconDiscoveryStrategy(
        {str(discovery_request.endpoint_url): found} if known else {}
    )

    assert await strategy.discover(discovery_request) == (
        found if known else FaviconNotFound()
    )


@pytest.mark.asyncio
async def test_in_memory_strategy_preserves_explicit_miss(
    discovery_request: FaviconDiscoveryRequest,
) -> None:
    strategy: FaviconDiscoveryStrategy = InMemoryFaviconDiscoveryStrategy(
        {str(discovery_request.endpoint_url): FaviconNotFound()}
    )

    assert await strategy.discover(discovery_request) == FaviconNotFound()
