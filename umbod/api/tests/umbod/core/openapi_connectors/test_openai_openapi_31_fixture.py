import json
from pathlib import Path
from typing import Any, cast

import pytest

from umbod.core.connectors.openapi.importing import InMemoryOpenApiCandidateImporter
from umbod.core.connectors.openapi.models import ImportedOpenApiCandidate, ObjectSchema


@pytest.fixture(scope="module")
def imported_openai_fixture() -> ImportedOpenApiCandidate:
    fixture_path = Path(__file__).parent / "fixtures" / "openai-openapi-3.1.json"
    candidate = cast(Any, json.loads(fixture_path.read_text()))
    return InMemoryOpenApiCandidateImporter().import_candidate(candidate)


def test_imports_stable_metadata_servers_and_operation_count(
    imported_openai_fixture: ImportedOpenApiCandidate,
) -> None:
    assert imported_openai_fixture.metadata.title == "OpenAI API"
    assert imported_openai_fixture.metadata.version == "2.3.0"
    assert (
        imported_openai_fixture.metadata.description
        == "The OpenAI REST API. Please see https://platform.openai.com/docs/api-reference for more details."
    )
    assert imported_openai_fixture.server_candidates == ("https://api.openai.com/v1",)
    assert len(imported_openai_fixture.endpoints) == 287
    assert len({endpoint.operation_id for endpoint in imported_openai_fixture.endpoints}) == 287


@pytest.mark.parametrize(
    ("operation_id", "method", "path"),
    [
        ("listModels", "get", "/models"),
        ("createChatCompletion", "post", "/chat/completions"),
        ("createEmbedding", "post", "/embeddings"),
        ("deleteModel", "delete", "/models/{model}"),
    ],
)
def test_imports_representative_operations(
    imported_openai_fixture: ImportedOpenApiCandidate, operation_id: str, method: str, path: str
) -> None:
    endpoint = next(
        item for item in imported_openai_fixture.endpoints if item.operation_id == operation_id
    )

    assert endpoint.method == method
    assert endpoint.path == path


def test_resolves_representative_parameters_and_json_schemas(
    imported_openai_fixture: ImportedOpenApiCandidate,
) -> None:
    delete_model = next(
        item for item in imported_openai_fixture.endpoints if item.operation_id == "deleteModel"
    )
    embedding = next(
        item for item in imported_openai_fixture.endpoints if item.operation_id == "createEmbedding"
    )
    list_models = next(
        item for item in imported_openai_fixture.endpoints if item.operation_id == "listModels"
    )
    list_assistants = next(
        item for item in imported_openai_fixture.endpoints if item.operation_id == "listAssistants"
    )

    assert [
        (parameter.name, parameter.location, parameter.required)
        for parameter in delete_model.parameters
    ] == [("model", "path", True)]
    assert [(parameter.name, parameter.required) for parameter in list_assistants.parameters] == [
        ("limit", False),
        ("order", False),
        ("after", False),
        ("before", False),
    ]
    embedding_request = cast(ObjectSchema, embedding.request_bodies[0].capability_schema)
    embedding_response = cast(ObjectSchema, embedding.response_bodies[0].capability_schema)
    models_response = cast(ObjectSchema, list_models.response_bodies[0].capability_schema)
    assert embedding_request.required == ("model", "input")
    assert set(embedding_request.properties) == {
        "input",
        "model",
        "encoding_format",
        "dimensions",
        "user",
    }
    assert set(embedding_response.properties) == {"data", "model", "object", "usage"}
    assert set(models_response.properties) == {"object", "data"}
