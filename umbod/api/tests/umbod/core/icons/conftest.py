import pytest

from umbod.core.icons import Favicon, FaviconDiscoveryRequest, FaviconFound


@pytest.fixture
def discovery_request() -> FaviconDiscoveryRequest:
    return FaviconDiscoveryRequest(
        endpoint_url="https://connector.example/mcp", advertised_icons=()
    )


@pytest.fixture
def found() -> FaviconFound:
    return FaviconFound(
        icon=Favicon(url="https://connector.example/icon.png", mime_type="image/png"),
        strategy="memory",
    )
