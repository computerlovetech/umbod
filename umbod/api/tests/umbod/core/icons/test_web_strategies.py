import pytest

from umbod.core.icons.adapters.in_memory_http import InMemoryFaviconHttpClient
from umbod.core.icons.http_models import FaviconHttpResponse
from umbod.core.icons.models import FaviconDiscoveryRequest, FaviconFound, FaviconNotFound
from umbod.core.icons.ports import FaviconDiscoveryStrategy
from umbod.core.icons.web_strategies import HtmlIconStrategy, OriginFaviconStrategy


PNG = b"\x89PNG\r\n\x1a\nimage"
ORIGIN = "https://example.com/"
ICON = "https://example.com/favicon.ico"


def discovery_request() -> FaviconDiscoveryRequest:
    return FaviconDiscoveryRequest(endpoint_url="https://example.com/mcp/tools?token=secret", advertised_icons=())


def response(url: str, content_type: str, body: bytes, status: int) -> FaviconHttpResponse:
    return FaviconHttpResponse(url=url, status=status, content_type=content_type, body=body)


@pytest.mark.asyncio
async def test_origin_ignores_endpoint_path_and_query() -> None:
    client = InMemoryFaviconHttpClient({ICON: response(ICON, "image/png", PNG, 200)})
    strategy: FaviconDiscoveryStrategy = OriginFaviconStrategy(client)
    result = await strategy.discover(discovery_request())
    assert isinstance(result, FaviconFound)
    assert result.icon.url == ICON
    assert result.strategy == "origin_favicon"
    assert [str(request.url) for request in client.requests] == [ICON]


@pytest.mark.parametrize(
    ("body", "declared_type", "expected_type"),
    [
        (PNG, "image/x-icon", "image/png"),
        (b"\x00\x00\x01\x00icon", "image/vnd.microsoft.icon", "image/x-icon"),
        (b"GIF87aimage", "image/gif", "image/gif"),
        (b"GIF89aimage", "image/gif", "image/gif"),
        (b"\xff\xd8\xffimage", "image/jpeg", "image/jpeg"),
        (b"RIFF1234WEBPimage", "image/webp", "image/webp"),
        (b'<svg xmlns="http://www.w3.org/2000/svg"/>', "image/svg+xml", "image/svg+xml"),
    ],
)
@pytest.mark.asyncio
async def test_image_signature_determines_returned_mime_type(body: bytes, declared_type: str, expected_type: str) -> None:
    client = InMemoryFaviconHttpClient({ICON: response(ICON, declared_type, body, 200)})
    strategy: FaviconDiscoveryStrategy = OriginFaviconStrategy(client)
    result = await strategy.discover(discovery_request())
    assert isinstance(result, FaviconFound)
    assert result.icon.mime_type == expected_type


@pytest.mark.parametrize(
    ("body", "content_type", "status"),
    [
        (b"<html>not an icon</html>", "image/png", 200),
        (PNG, "text/html", 200),
        (PNG, "application/octet-stream", 200),
        (PNG, "", 200),
        (PNG, "image/png", 404),
        (b"", "image/png", 200),
        (b'<!DOCTYPE svg [<!ENTITY x "x">]><svg/>', "image/svg+xml", 200),
        (b"<html><svg/></html>", "image/svg+xml", 200),
    ],
)
@pytest.mark.asyncio
async def test_origin_rejects_nonimages_and_unsuccessful_responses(body: bytes, content_type: str, status: int) -> None:
    client = InMemoryFaviconHttpClient({ICON: response(ICON, content_type, body, status)})
    strategy: FaviconDiscoveryStrategy = OriginFaviconStrategy(client)
    assert isinstance(await strategy.discover(discovery_request()), FaviconNotFound)


@pytest.mark.asyncio
async def test_unavailable_origin_is_a_miss() -> None:
    strategy: FaviconDiscoveryStrategy = OriginFaviconStrategy(InMemoryFaviconHttpClient({}))
    assert isinstance(await strategy.discover(discovery_request()), FaviconNotFound)


@pytest.mark.parametrize("href", ["assets/icon.png", "https://cdn.example.com/icon.png"])
@pytest.mark.asyncio
async def test_html_resolves_links_from_final_document_url_and_case_insensitive_rel(href: str) -> None:
    target = "https://example.com/site/assets/icon.png" if href.startswith("assets") else href
    client = InMemoryFaviconHttpClient({
        ORIGIN: response("https://example.com/site/index.html", "text/html", f'<LINK REL="SHORTCUT IcOn" href="{href}">'.encode(), 200),
        target: response(target, "image/png", PNG, 200),
    })
    strategy: FaviconDiscoveryStrategy = HtmlIconStrategy(client)
    result = await strategy.discover(discovery_request())
    assert isinstance(result, FaviconFound)
    assert result.icon.url == target
    assert result.strategy == "html_icon"
    assert [str(request.url) for request in client.requests] == [ORIGIN, target]


@pytest.mark.parametrize("html", [b"<html></html>", b'<link rel="stylesheet" href="style.css">'])
@pytest.mark.asyncio
async def test_html_without_icon_links_is_a_miss(html: bytes) -> None:
    client = InMemoryFaviconHttpClient({ORIGIN: response(ORIGIN, "text/html", html, 200)})
    strategy: FaviconDiscoveryStrategy = HtmlIconStrategy(client)
    assert isinstance(await strategy.discover(discovery_request()), FaviconNotFound)
    assert len(client.requests) == 1


@pytest.mark.asyncio
async def test_html_uses_first_valid_candidate_and_stops_fetching() -> None:
    html = b'<link rel="icon" href="bad"><link rel="apple-touch-icon" href="good"><link rel="icon" href="later">'
    good = ORIGIN + "good"
    client = InMemoryFaviconHttpClient({
        ORIGIN: response(ORIGIN, "text/html", html, 200),
        ORIGIN + "bad": response(ORIGIN + "bad", "image/png", b"<html/>", 200),
        good: response(good, "image/png", PNG, 200),
    })
    strategy: FaviconDiscoveryStrategy = HtmlIconStrategy(client)
    result = await strategy.discover(discovery_request())
    assert isinstance(result, FaviconFound)
    assert result.icon.url == good
    assert [str(request.url) for request in client.requests] == [ORIGIN, ORIGIN + "bad", good]


@pytest.mark.parametrize("href", ["javascript:alert(1)", "data:image/png;base64,AAAA", "file:///etc/passwd", "https://[invalid]/icon", "https://example.com:99999/icon"])
@pytest.mark.asyncio
async def test_invalid_html_candidate_does_not_prevent_following_valid_link(href: str) -> None:
    html = f'<link rel="icon" href="{href}"><link rel="icon" href="/favicon.ico">'.encode()
    client = InMemoryFaviconHttpClient({
        ORIGIN: response(ORIGIN, "text/html", html, 200),
        ICON: response(ICON, "image/png", PNG, 200),
    })
    strategy: FaviconDiscoveryStrategy = HtmlIconStrategy(client)
    result = await strategy.discover(discovery_request())
    assert isinstance(result, FaviconFound)
    assert [str(request.url) for request in client.requests] == [ORIGIN, ICON]


@pytest.mark.asyncio
async def test_unsuccessful_html_document_does_not_provide_icon_links() -> None:
    client = InMemoryFaviconHttpClient({
        ORIGIN: response(ORIGIN, "text/html", b'<link rel="icon" href="/favicon.ico">', 404),
        ICON: response(ICON, "image/png", PNG, 200),
    })
    strategy: FaviconDiscoveryStrategy = HtmlIconStrategy(client)
    assert isinstance(await strategy.discover(discovery_request()), FaviconNotFound)
    assert [str(request.url) for request in client.requests] == [ORIGIN]
