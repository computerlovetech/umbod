import pytest
from pydantic import TypeAdapter, ValidationError

from umbod.core.icons import (
    Favicon,
    FaviconDiscoveryRequest,
    FaviconDiscoveryResult,
    FaviconDiscoveryTimedOut,
    FaviconFound,
    FaviconNotFound,
)


@pytest.mark.parametrize(
    "url",
    [
        "https://icons.example/icon.png",
        "http://icons.example/favicon.ico",
        "data:image/png;base64,YQ==",
        "data:image/svg+xml,%3Csvg%3E%3C/svg%3E",
    ],
)
def test_icon_accepts_web_and_image_data_urls(url: str) -> None:
    assert Favicon(url=url, mime_type="image/png").url == url


@pytest.mark.parametrize(
    "url",
    [
        "",
        "/favicon.ico",
        "ftp://icons.example/icon.png",
        "javascript:alert(1)",
        "data:text/html,hi",
        "data:image/png",
        "https://user:password@icons.example/icon.png",
        "https://user@icons.example/icon.png",
    ],
)
def test_icon_rejects_other_urls(url: str) -> None:
    with pytest.raises(ValidationError):
        Favicon(url=url, mime_type="image/png")


def test_icon_requires_mime_type() -> None:
    with pytest.raises(ValidationError):
        Favicon.model_validate({"url": "https://icons.example/icon.png"})


def test_request_requires_advertised_icons() -> None:
    with pytest.raises(ValidationError):
        FaviconDiscoveryRequest.model_validate(
            {"endpoint_url": "https://connector.example"}
        )


@pytest.mark.parametrize(
    "url",
    [
        "data:image/png,hi",
        "ftp://connector.example",
        "/mcp",
        "https://user:password@connector.example/mcp",
        "https://user@connector.example/mcp",
    ],
)
def test_request_rejects_non_http_endpoints(url: str) -> None:
    with pytest.raises(ValidationError):
        FaviconDiscoveryRequest(endpoint_url=url, advertised_icons=())


@pytest.mark.parametrize(
    "model",
    [
        Favicon(url="https://icons.example/icon.png", mime_type="image/png"),
        FaviconDiscoveryRequest(
            endpoint_url="https://connector.example", advertised_icons=()
        ),
        FaviconFound(
            icon=Favicon(url="https://icons.example/icon.png", mime_type="image/png"),
            strategy="test",
        ),
        FaviconNotFound(),
        FaviconDiscoveryTimedOut(),
    ],
)
def test_models_are_frozen(
    model: Favicon
    | FaviconDiscoveryRequest
    | FaviconFound
    | FaviconNotFound
    | FaviconDiscoveryTimedOut,
) -> None:
    field = next(iter(type(model).model_fields))
    with pytest.raises(ValidationError, match="frozen"):
        setattr(model, field, getattr(model, field))


@pytest.mark.parametrize("result", [FaviconNotFound(), FaviconDiscoveryTimedOut()])
def test_result_union_roundtrips_discriminated_status(
    result: FaviconNotFound | FaviconDiscoveryTimedOut,
) -> None:
    adapter = TypeAdapter(FaviconDiscoveryResult)

    assert adapter.validate_python(result.model_dump()) == result


def test_found_result_roundtrips_discriminated_status(found: FaviconFound) -> None:
    assert (
        TypeAdapter(FaviconDiscoveryResult).validate_python(found.model_dump()) == found
    )
