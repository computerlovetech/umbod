from html.parser import HTMLParser
from typing import Optional
from urllib.parse import urldefrag, urljoin, urlsplit, urlunsplit
from xml.etree import ElementTree

from .http_models import FaviconHttpRequest, FaviconHttpResponse, FaviconHttpResult
from .http_ports import FaviconHttpClient
from .models import Favicon, FaviconDiscoveryRequest, FaviconFound, FaviconNotFound


class OriginFaviconStrategy:
    def __init__(self, client: FaviconHttpClient) -> None:
        self._client = client

    async def discover(self, request: FaviconDiscoveryRequest) -> FaviconFound | FaviconNotFound:
        response = await self._client.fetch(FaviconHttpRequest(url=urljoin(_origin(request), "favicon.ico")))
        return _image_result(response, "origin_favicon")


class HtmlIconStrategy:
    def __init__(self, client: FaviconHttpClient) -> None:
        self._client = client

    async def discover(self, request: FaviconDiscoveryRequest) -> FaviconFound | FaviconNotFound:
        response = await self._client.fetch(FaviconHttpRequest(url=_origin(request)))
        if (
            not isinstance(response, FaviconHttpResponse)
            or response.status != 200
            or response.content_type not in {"text/html", "application/xhtml+xml"}
        ):
            return FaviconNotFound()
        parser = _IconLinks(str(response.url))
        parser.feed(response.body.decode("utf-8", errors="replace"))
        for url in parser.urls:
            try:
                image_request = FaviconHttpRequest(url=url)
            except ValueError:
                continue
            image = await self._client.fetch(image_request)
            result = _image_result(image, "html_icon")
            if isinstance(result, FaviconFound):
                return result
        return FaviconNotFound()


class _IconLinks(HTMLParser):
    def __init__(self, document_url: str) -> None:
        super().__init__()
        self._document_url = document_url
        self.urls: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, Optional[str]]]) -> None:
        attributes = dict(attrs)
        relation = (attributes.get("rel") or "").lower().split()
        href = attributes.get("href")
        if tag == "link" and href and len(self.urls) < 8 and {"icon", "apple-touch-icon"}.intersection(relation):
            try:
                url = urldefrag(urljoin(self._document_url, href))[0]
                if urlsplit(url).scheme not in {"http", "https"}:
                    return
            except ValueError:
                return
            if url not in self.urls:
                self.urls.append(url)


def _origin(request: FaviconDiscoveryRequest) -> str:
    parts = urlsplit(str(request.endpoint_url))
    return urlunsplit((parts.scheme, parts.netloc, "/", "", ""))


def _image_result(response: FaviconHttpResult, strategy: str) -> FaviconFound | FaviconNotFound:
    if not isinstance(response, FaviconHttpResponse) or response.status != 200:
        return FaviconNotFound()
    media_type = _image_media_type(response.body)
    if not media_type or not response.content_type.startswith("image/"):
        return FaviconNotFound()
    return FaviconFound(icon=Favicon(url=str(response.url), mime_type=media_type), strategy=strategy)


def _image_media_type(body: bytes) -> str:
    signatures = (
        (b"\x89PNG\r\n\x1a\n", "image/png"),
        (b"\x00\x00\x01\x00", "image/x-icon"),
        (b"GIF87a", "image/gif"),
        (b"GIF89a", "image/gif"),
        (b"\xff\xd8\xff", "image/jpeg"),
    )
    for signature, media_type in signatures:
        if body.startswith(signature):
            return media_type
    if body.startswith(b"RIFF") and body[8:12] == b"WEBP":
        return "image/webp"
    if b"<!DOCTYPE" in body.upper() or b"<!ENTITY" in body.upper():
        return ""
    try:
        root = ElementTree.fromstring(body)
    except ElementTree.ParseError:
        return ""
    return "image/svg+xml" if root.tag in {"svg", "{http://www.w3.org/2000/svg}svg"} else ""
