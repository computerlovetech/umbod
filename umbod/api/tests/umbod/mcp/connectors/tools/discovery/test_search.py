import pytest

from umbod.mcp.connectors.tools.discovery.search import (
    ConnectorToolSearch,
    ConnectorToolSearchCandidate,
    ConnectorToolSearchInput,
    InMemoryFuzzyConnectorToolSearch,
)


def _candidate(
    tool_name: str,
    *,
    connector_id: str = "service",
    connector_display_name: str = "Service",
    operation_name: str = "action",
    description: str = "",
    search_hints: tuple[str, ...] = (),
    properties: tuple[str, ...] = (),
) -> ConnectorToolSearchCandidate:
    return ConnectorToolSearchCandidate(
        tool_name=tool_name,
        description=description,
        connector_id=connector_id,
        connector_display_name=connector_display_name,
        operation_name=operation_name,
        input_schema={
            "type": "object",
            "properties": {name: {"type": "string"} for name in properties},
        },
        search_hints=search_hints,
    )


def _search(
    query: str, candidates: list[ConnectorToolSearchCandidate], limit: int = 10
) -> list[str]:
    search: ConnectorToolSearch = InMemoryFuzzyConnectorToolSearch()
    result = search.search(
        ConnectorToolSearchInput(query=query, candidates=candidates, limit=limit)
    )
    return [match.tool_name for match in result.matches]


def test_exact_connector_display_name_outranks_incidental_description_match() -> None:
    exact = _candidate("calendar_list", connector_display_name="Calendar")
    incidental = _candidate(
        "notes_find", connector_display_name="Notes", description="Calendar calendar"
    )

    assert _search("calendar", [incidental, exact]) == ["calendar_list", "notes_find"]


def test_exact_operation_name_outranks_incidental_schema_and_description_matches() -> None:
    exact = _candidate("calendar_create_event", operation_name="create_event")
    incidental = _candidate(
        "calendar_search",
        operation_name="search",
        description="Create event",
        properties=("create_event",),
    )

    assert _search("create event", [incidental, exact])[0] == "calendar_create_event"


def test_curated_search_hints_support_synonym_queries() -> None:
    event = _candidate(
        "calendar_create_event",
        operation_name="create_event",
        description="Create a calendar event",
        search_hints=("book time", "schedule meeting"),
    )

    assert _search("book time", [event]) == ["calendar_create_event"]


def test_schema_property_names_have_lower_weight_than_description() -> None:
    described = _candidate("files_find", description="Find customer")
    schema_only = _candidate("users_get", properties=("customer",))

    assert _search("customer", [schema_only, described]) == ["files_find", "users_get"]


def test_unmatched_query_returns_no_matches() -> None:
    assert _search("unrelated", [_candidate("calendar_list")]) == []


def test_omitted_and_empty_connector_scope_preserve_global_search() -> None:
    candidates = [
        _candidate("calendar_list", connector_id="calendar", description="shared"),
        _candidate("notes_list", connector_id="notes", description="shared"),
    ]
    search: ConnectorToolSearch = InMemoryFuzzyConnectorToolSearch()

    omitted = search.search(ConnectorToolSearchInput(query="shared", candidates=candidates))
    empty = search.search(
        ConnectorToolSearchInput(query="shared", candidates=candidates, connector_ids=[])
    )

    assert (
        [match.tool_name for match in omitted.matches]
        == [match.tool_name for match in empty.matches]
        == ["calendar_list", "notes_list"]
    )
    assert omitted.matches[0].model_dump().keys() == empty.matches[0].model_dump().keys()


def test_connector_scope_is_normalized_to_immutable_tuple() -> None:
    search_input = ConnectorToolSearchInput(
        query="shared", candidates=[], connector_ids=["calendar", "notes"]
    )

    assert search_input.connector_ids == ("calendar", "notes")


def test_one_and_multiple_connector_scopes_intersect_candidates_before_ranking() -> None:
    candidates = [
        _candidate("calendar_list", connector_id="calendar", description="shared"),
        _candidate("notes_list", connector_id="notes", description="shared"),
        _candidate("tasks_list", connector_id="tasks", description="shared"),
    ]
    search: ConnectorToolSearch = InMemoryFuzzyConnectorToolSearch()

    one = search.search(
        ConnectorToolSearchInput(query="shared", candidates=candidates, connector_ids=["notes"])
    )
    multiple = search.search(
        ConnectorToolSearchInput(
            query="shared", candidates=candidates, connector_ids=["calendar", "tasks"]
        )
    )

    assert [match.connector_id for match in one.matches] == ["notes"]
    assert [match.connector_id for match in multiple.matches] == ["calendar", "tasks"]


def test_mixed_known_and_unknown_scope_returns_only_known_intersection() -> None:
    search: ConnectorToolSearch = InMemoryFuzzyConnectorToolSearch()
    candidates = [_candidate("calendar_list", connector_id="calendar", description="shared")]

    result = search.search(
        ConnectorToolSearchInput(
            query="shared", candidates=candidates, connector_ids=["unknown", "calendar"]
        )
    )

    assert [match.connector_id for match in result.matches] == ["calendar"]


def test_unknown_only_scope_returns_same_empty_output_as_denied_candidate_absence() -> None:
    search: ConnectorToolSearch = InMemoryFuzzyConnectorToolSearch()
    candidate = _candidate("calendar_list", connector_id="calendar", description="shared")

    unknown = search.search(
        ConnectorToolSearchInput(query="shared", candidates=[candidate], connector_ids=["unknown"])
    )
    absent = search.search(
        ConnectorToolSearchInput(query="shared", candidates=[], connector_ids=["calendar"])
    )

    assert unknown.model_dump() == absent.model_dump() == {"matches": []}


def test_equal_scores_are_ordered_deterministically_by_public_identity() -> None:
    candidates = [
        _candidate("z_tool", description="shared"),
        _candidate("a_tool", description="shared"),
    ]

    assert _search("shared", candidates) == ["a_tool", "z_tool"]


def test_limit_is_applied_after_ranking() -> None:
    candidates = [
        _candidate("schema", properties=("calendar",)),
        _candidate("operation", operation_name="calendar"),
        _candidate("description", description="calendar"),
    ]

    assert _search("calendar", candidates, limit=2) == ["operation", "description"]


def test_existing_candidate_constructor_remains_compatible() -> None:
    candidate = ConnectorToolSearchCandidate(
        tool_name="service_action",
        description="Action",
        connector_id="service",
        operation_name="action",
        input_schema={"type": "object"},
    )

    assert candidate.connector_display_name == "service"
    assert candidate.search_hints == ()


def test_public_match_serialization_has_byte_compatible_fields_only() -> None:
    candidate = _candidate(
        "calendar_create_event",
        connector_id="calendar",
        connector_display_name="Calendar",
        operation_name="create_event",
        description="Create event",
        search_hints=("book time",),
    )
    search: ConnectorToolSearch = InMemoryFuzzyConnectorToolSearch()

    match = search.search(ConnectorToolSearchInput(query="book", candidates=[candidate])).matches[0]

    assert list(match.model_dump().keys()) == [
        "tool_name",
        "description",
        "connector_id",
        "operation_name",
        "input_schema",
        "relevance_score",
    ]
    assert "connector_display_name" not in match.model_dump_json()
    assert "search_hints" not in match.model_dump_json()


@pytest.mark.parametrize("query", ["CreateEvent", "create_event", "create-event"])
def test_token_normalization_handles_common_identifier_styles(query: str) -> None:
    candidate = _candidate("calendar_create_event", operation_name="createEvent")

    assert _search(query, [candidate]) == ["calendar_create_event"]
