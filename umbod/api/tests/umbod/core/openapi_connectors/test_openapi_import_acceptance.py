from collections.abc import Callable
from typing import Any

import pytest

from umbod.core.connectors.openapi.errors import OpenApiCandidateValidationError
from umbod.core.connectors.openapi.importing import (
    InMemoryOpenApiCandidateImporter,
    OpenApiCandidateImporter,
)
from umbod.core.connectors.openapi.models import (
    ArraySchema,
    ObjectSchema,
    PrimitiveSchema,
)

Candidate = dict[str, Any]


def _importer() -> OpenApiCandidateImporter:
    return InMemoryOpenApiCandidateImporter()


def _candidate(paths: dict[str, Any]) -> Candidate:
    return {
        "openapi": "3.1.0",
        "info": {"title": "Pets", "version": "1.2.3"},
        "paths": paths,
    }


def _operation(operation_id: str) -> dict[str, Any]:
    return {"operationId": operation_id, "responses": {"200": {"description": "OK"}}}


def _issues(candidate: object) -> set[tuple[str, tuple[str | int, ...]]]:
    with pytest.raises(OpenApiCandidateValidationError) as captured:
        _importer().import_candidate(candidate)
    return {(issue.code, issue.location) for issue in captured.value.issues}


def test_imports_minimal_document_metadata_and_normalizes_absent_values() -> None:
    imported = _importer().import_candidate(_candidate({"/pets": {"get": _operation("listPets")}}))

    assert imported.metadata.title == "Pets"
    assert imported.metadata.version == "1.2.3"
    assert imported.metadata.description == ""
    assert imported.endpoints[0].summary == ""
    assert imported.endpoints[0].description == ""
    assert imported.endpoints[0].parameters == ()
    assert imported.endpoints[0].request_bodies == ()
    assert imported.endpoints[0].response_bodies == ()


def test_normalizes_operation_contract() -> None:
    candidate = _candidate(
        {
            "/pets/{petId}": {
                "post": {
                    **_operation("replacePet"),
                    "summary": "Replace",
                    "description": "Replaces a pet",
                }
            }
        }
    )

    endpoint = _importer().import_candidate(candidate).endpoints[0]

    assert (endpoint.operation_id, endpoint.method, endpoint.path) == (
        "replacePet",
        "post",
        "/pets/{petId}",
    )
    assert (endpoint.summary, endpoint.description) == ("Replace", "Replaces a pet")


@pytest.mark.parametrize(
    "method", ["get", "put", "post", "delete", "options", "head", "patch", "trace"]
)
def test_supports_every_openapi_http_method(method: str) -> None:
    imported = _importer().import_candidate(_candidate({"/resource": {method: _operation(method)}}))

    assert imported.endpoints[0].method == method


def test_orders_endpoints_by_path_then_fixed_method_order() -> None:
    candidate = _candidate(
        {
            "/z": {"delete": _operation("zDelete"), "get": _operation("zGet")},
            "/a": {"patch": _operation("aPatch"), "post": _operation("aPost")},
        }
    )

    imported = _importer().import_candidate(candidate)

    assert [(endpoint.path, endpoint.method) for endpoint in imported.endpoints] == [
        ("/a", "post"),
        ("/a", "patch"),
        ("/z", "get"),
        ("/z", "delete"),
    ]


def test_normalizes_path_and_query_parameters_and_explicit_schema_variants() -> None:
    operation = _operation("findPets") | {
        "parameters": [
            {"name": "petId", "in": "path", "required": True, "schema": {"type": "string"}},
            {"name": "limit", "in": "query", "schema": {"type": "integer", "format": "int32"}},
            {
                "name": "tags",
                "in": "query",
                "schema": {"type": "array", "items": {"type": "string"}},
            },
            {
                "name": "filter",
                "in": "query",
                "schema": {
                    "type": "object",
                    "properties": {"active": {"type": "boolean"}},
                    "required": ["active"],
                },
            },
        ]
    }

    parameters = (
        _importer()
        .import_candidate(_candidate({"/pets/{petId}": {"get": operation}}))
        .endpoints[0]
        .parameters
    )

    assert [
        (parameter.name, parameter.location, parameter.required) for parameter in parameters
    ] == [
        ("petId", "path", True),
        ("limit", "query", False),
        ("tags", "query", False),
        ("filter", "query", False),
    ]
    assert isinstance(parameters[0].capability_schema, PrimitiveSchema)
    assert isinstance(parameters[2].capability_schema, ArraySchema)
    assert isinstance(parameters[3].capability_schema, ObjectSchema)


def test_imports_header_parameters_and_root_https_server_candidates() -> None:
    candidate = _candidate(
        {
            "/pets": {
                "get": _operation("listPets")
                | {
                    "parameters": [
                        {"name": "X-Trace", "in": "header", "schema": {"type": "string"}}
                    ]
                }
            }
        }
    )
    candidate["servers"] = [{"url": "https://api.example.test/v1"}]

    imported = _importer().import_candidate(candidate)

    assert imported.server_candidates == ("https://api.example.test/v1",)
    assert imported.endpoints[0].parameters[0].location == "header"


@pytest.mark.parametrize(
    "url",
    [
        "/v1",
        "http://api.example.test",
        "not a url",
        "https://user@example.test",
        "https://api.example.test:invalid",
        "https://{tenant}.example.test",
    ],
)
def test_rejects_unsafe_or_non_absolute_root_servers(url: str) -> None:
    candidate = _candidate({"/pets": {"get": _operation("listPets")}})
    candidate["servers"] = [{"url": url}]

    assert ("unsupported_server", ("servers", 0, "url")) in _issues(candidate)


def test_rejects_server_variables_and_operation_or_path_overrides() -> None:
    candidate = _candidate(
        {
            "/pets": {
                "servers": [{"url": "https://path.example.test"}],
                "get": _operation("listPets")
                | {"servers": [{"url": "https://operation.example.test"}]},
            }
        }
    )
    candidate["servers"] = [
        {"url": "https://{tenant}.example.test", "variables": {"tenant": {"default": "a"}}}
    ]

    issues = _issues(candidate)

    assert ("unsupported_server", ("servers", 0, "variables")) in issues
    assert ("unsupported_server_override", ("paths", "/pets", "servers")) in issues
    assert ("unsupported_server_override", ("paths", "/pets", "get", "servers")) in issues


@pytest.mark.parametrize(
    ("parameter", "field"),
    [
        ({"name": "q", "in": "query", "style": "matrix"}, "style"),
        ({"name": "q", "in": "query", "style": "spaceDelimited", "explode": True}, "explode"),
        ({"name": "X", "in": "header", "style": "form"}, "style"),
        ({"name": "q", "in": "query", "style": "deepObject", "explode": False}, "explode"),
        ({"name": "q", "in": "query", "allowReserved": True}, "allowReserved"),
    ],
)
def test_omits_parameter_serialization_outside_deterministic_defaults(
    parameter: dict[str, Any], field: str
) -> None:
    parameter["schema"] = {"type": "string"}
    operation = _operation("search") | {"parameters": [parameter]}

    imported = _importer().import_candidate(_candidate({"/search": {"get": operation}}))

    assert field
    assert imported.endpoints[0].parameters == ()


def test_accepts_explicit_standard_parameter_serialization_defaults() -> None:
    operation = _operation("getPet") | {
        "parameters": [
            {
                "name": "id",
                "in": "path",
                "required": True,
                "style": "simple",
                "explode": False,
                "schema": {"type": "string"},
            },
            {
                "name": "q",
                "in": "query",
                "style": "form",
                "explode": True,
                "allowReserved": False,
                "schema": {"type": "string"},
            },
            {
                "name": "X",
                "in": "header",
                "style": "simple",
                "explode": False,
                "schema": {"type": "string"},
            },
        ]
    }

    imported = _importer().import_candidate(_candidate({"/pets/{id}": {"get": operation}}))

    assert [parameter.location for parameter in imported.endpoints[0].parameters] == [
        "path",
        "query",
        "header",
    ]


def test_merges_path_parameters_with_operation_override() -> None:
    candidate = _candidate(
        {
            "/pets/{petId}": {
                "parameters": [
                    {
                        "name": "petId",
                        "in": "path",
                        "required": True,
                        "description": "path",
                        "schema": {"type": "string"},
                    },
                    {"name": "locale", "in": "query", "schema": {"type": "string"}},
                ],
                "get": _operation("getPet")
                | {
                    "parameters": [
                        {
                            "name": "locale",
                            "in": "query",
                            "description": "operation",
                            "schema": {"type": "string"},
                        }
                    ]
                },
            }
        }
    )

    parameters = _importer().import_candidate(candidate).endpoints[0].parameters

    assert [(parameter.name, parameter.description) for parameter in parameters] == [
        ("petId", "path"),
        ("locale", "operation"),
    ]


def test_normalizes_json_request_and_response_bodies() -> None:
    operation = _operation("createPet") | {
        "requestBody": {
            "required": True,
            "description": "Pet input",
            "content": {
                "application/json": {
                    "schema": {"type": "object", "properties": {"name": {"type": "string"}}}
                }
            },
        },
        "responses": {
            "201": {
                "description": "Created",
                "content": {
                    "application/json": {
                        "schema": {"type": "object", "properties": {"id": {"type": "integer"}}}
                    }
                },
            },
            "400": {"description": "Bad request", "content": {"application/json": {}}},
        },
    }

    endpoint = _importer().import_candidate(_candidate({"/pets": {"post": operation}})).endpoints[0]

    assert [
        (body.media_type, body.required, body.description) for body in endpoint.request_bodies
    ] == [("application/json", True, "Pet input")]
    assert [
        (body.status_code, body.media_type, body.description) for body in endpoint.response_bodies
    ] == [("201", "application/json", "Created")]


@pytest.mark.parametrize("candidate", [None, [], "document", 3])
def test_rejects_invalid_top_level_candidate_dto(candidate: object) -> None:
    assert ("invalid_candidate", ()) in _issues(candidate)


@pytest.mark.parametrize(
    ("version", "code"),
    [
        (None, "missing_openapi_version"),
        ("2.0", "unsupported_openapi_version"),
        ("3.2.0", "unsupported_openapi_version"),
    ],
)
def test_rejects_missing_or_unsupported_openapi_version(version: object, code: str) -> None:
    candidate = _candidate({"/pets": {"get": _operation("listPets")}})
    if version is None:
        del candidate["openapi"]
    else:
        candidate["openapi"] = version

    assert (code, ("openapi",)) in _issues(candidate)


@pytest.mark.parametrize(
    ("mutate", "code", "location"),
    [
        (lambda candidate: candidate.update(info=[]), "invalid_info", ("info",)),
        (lambda candidate: candidate.update(paths=[]), "invalid_paths", ("paths",)),
        (
            lambda candidate: candidate["paths"].update({"/bad": []}),
            "invalid_path_item",
            ("paths", "/bad"),
        ),
        (
            lambda candidate: candidate["paths"]["/pets"].update(get=[]),
            "invalid_operation",
            ("paths", "/pets", "get"),
        ),
        (
            lambda candidate: candidate["paths"]["/pets"]["get"].update(parameters={}),
            "invalid_parameters",
            ("paths", "/pets", "get", "parameters"),
        ),
        (
            lambda candidate: candidate["paths"]["/pets"]["get"].update(responses=[]),
            "invalid_responses",
            ("paths", "/pets", "get", "responses"),
        ),
    ],
)
def test_rejects_malformed_document_sections(
    mutate: Callable[[Candidate], object], code: str, location: tuple[str | int, ...]
) -> None:
    candidate = _candidate({"/pets": {"get": _operation("listPets")}})
    mutate(candidate)

    assert (code, location) in _issues(candidate)


def test_rejects_missing_and_duplicate_operation_ids() -> None:
    candidate = _candidate(
        {
            "/a": {"get": _operation("same")},
            "/b": {"post": _operation("same"), "get": {"responses": {}}},
        }
    )

    issues = _issues(candidate)

    assert ("duplicate_operation_id", ("paths", "/b", "post", "operationId")) in issues
    assert ("missing_operation_id", ("paths", "/b", "get", "operationId")) in issues


def test_accepts_empty_paths() -> None:
    imported = _importer().import_candidate(_candidate({}))

    assert imported.endpoints == ()


@pytest.mark.parametrize(
    ("fragment", "location"),
    [
        ({"$ref": "#/paths/pets"}, ("paths", "/pets", "$ref")),
        ({"get": {"$ref": "#/components/operations/get"}}, ("paths", "/pets", "get", "$ref")),
        (
            {"get": _operation("get") | {"responses": {"$ref": "#/components/responses/all"}}},
            ("paths", "/pets", "get", "responses", "$ref"),
        ),
        (
            {"get": _operation("get") | {"requestBody": {"content": {}, "$ref": "remote"}}},
            ("paths", "/pets", "get", "requestBody", "$ref"),
        ),
    ],
)
def test_rejects_references_in_every_execution_structure(
    fragment: dict[str, Any], location: tuple[str | int, ...]
) -> None:
    assert ("unsupported_reference", location) in _issues(_candidate({"/pets": fragment}))


@pytest.mark.parametrize(
    ("operation_fragment", "location"),
    [
        (
            {"requestBody": {"content": {"application/json": {"$ref": "remote"}}}},
            ("paths", "/pets", "post", "requestBody", "content", "application/json", "$ref"),
        ),
        (
            {
                "responses": {
                    "200": {
                        "description": "OK",
                        "content": {"application/json": {"$ref": "#/components/mediaTypes/Pet"}},
                    }
                }
            },
            (
                "paths",
                "/pets",
                "post",
                "responses",
                "200",
                "content",
                "application/json",
                "$ref",
            ),
        ),
    ],
)
def test_rejects_references_in_request_and_response_media_sections(
    operation_fragment: dict[str, Any], location: tuple[str | int, ...]
) -> None:
    operation = _operation("createPet") | operation_fragment

    assert ("unsupported_reference", location) in _issues(
        _candidate({"/pets": {"post": operation}})
    )


def test_rejects_references_encountered_inside_root_server_structures() -> None:
    candidate = _candidate({"/pets": {"get": _operation("listPets")}})
    candidate["servers"] = [
        {
            "url": "https://{tenant}.example.test",
            "variables": {
                "tenant": {"default": "a", "$ref": "#/components/serverVariables/Tenant"}
            },
        }
    ]

    assert (
        "unsupported_reference",
        ("servers", 0, "variables", "tenant", "$ref"),
    ) in _issues(candidate)


def test_reports_operation_id_findings_deterministically_alongside_other_errors() -> None:
    candidate = _candidate(
        {
            "/b": {"post": _operation("same")},
            "/a": {
                "get": _operation("same") | {"responses": []},
                "post": {"responses": {}},
            },
        }
    )

    with pytest.raises(OpenApiCandidateValidationError) as captured:
        _importer().import_candidate(candidate)

    assert [(issue.code, issue.location) for issue in captured.value.issues] == [
        ("invalid_responses", ("paths", "/a", "get", "responses")),
        ("missing_operation_id", ("paths", "/a", "post", "operationId")),
        ("duplicate_operation_id", ("paths", "/b", "post", "operationId")),
    ]


def test_accepts_local_schema_references_and_composition() -> None:
    operation = _operation("search") | {
        "requestBody": {
            "content": {
                "application/json": {
                    "schema": {"oneOf": [{"$ref": "#/components/schemas/Pet"}, {"type": "string"}]}
                }
            }
        }
    }
    candidate = _candidate({"/search": {"get": operation}})
    candidate["components"] = {"schemas": {"Pet": {"type": "string"}}}

    imported = _importer().import_candidate(candidate)

    assert imported.endpoints[0].request_bodies[0].capability_schema.type == "composition"


def test_rejects_external_schema_reference() -> None:
    operation = _operation("search") | {
        "parameters": [
            {"name": "value", "in": "query", "schema": {"$ref": "https://example.test/pet.json"}}
        ]
    }

    assert (
        "unsupported_reference",
        ("paths", "/search", "get", "parameters", 0, "schema", "$ref"),
    ) in _issues(_candidate({"/search": {"get": operation}}))
