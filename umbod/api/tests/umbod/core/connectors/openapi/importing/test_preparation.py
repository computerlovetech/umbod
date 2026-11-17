import pytest

from umbod.core.connectors.openapi.importing import (
    DefaultOpenApiImportPreparer,
    InMemoryOpenApiCandidateImporter,
    OpenApiServerSelectionRequired,
)
from umbod.core.connectors.openapi.management import ImportOpenApiCatalog


def _request(server_urls: tuple[str, ...]) -> ImportOpenApiCatalog:
    source_document: dict[str, object] = {
        "openapi": "3.1.0",
        "info": {"title": "Inventory", "version": "1"},
        "servers": [{"url": url} for url in server_urls],
        "paths": {
            "/items": {
                "get": {
                    "operationId": "listItems",
                    "responses": {"200": {"description": "OK"}},
                }
            }
        },
    }
    return ImportOpenApiCatalog(
        connector_id="inventory",
        source_document=source_document,
        candidate=InMemoryOpenApiCandidateImporter().import_candidate(source_document),
        approved_hosts=("api.example.test",),
    )


@pytest.mark.parametrize(
    "server_urls",
    [(), ("https://api.example.test",)],
)
def test_missing_selection_resolves_single_eligible_server(
    server_urls: tuple[str, ...],
) -> None:
    prepared = DefaultOpenApiImportPreparer().prepare(_request(server_urls))

    assert prepared.selected_server_url == "https://api.example.test"


@pytest.mark.parametrize(
    "server_urls",
    [
        ("https://other.example.test",),
        ("https://api.example.test/v1", "https://api.example.test/v2"),
    ],
)
def test_missing_selection_rejects_zero_or_multiple_eligible_servers(
    server_urls: tuple[str, ...],
) -> None:
    with pytest.raises(OpenApiServerSelectionRequired, match="one selected eligible server"):
        DefaultOpenApiImportPreparer().prepare(_request(server_urls))


def test_explicit_selection_resolves_multiple_eligible_servers() -> None:
    request = _request(("https://api.example.test/v1", "https://api.example.test/v2"))
    request = request.model_copy(update={"selected_server_url": "https://api.example.test/v2"})

    prepared = DefaultOpenApiImportPreparer().prepare(request)

    assert prepared.selected_server_url == "https://api.example.test/v2"


@pytest.mark.parametrize(
    "selected_server_url",
    ["", "https://other.example.test", "https://api.example.test/unlisted"],
)
def test_explicit_selection_must_match_an_eligible_server(selected_server_url: str) -> None:
    request = _request(("https://api.example.test",))
    request = request.model_copy(update={"selected_server_url": selected_server_url})

    with pytest.raises(ValueError, match="approved exact host"):
        DefaultOpenApiImportPreparer().prepare(request)
