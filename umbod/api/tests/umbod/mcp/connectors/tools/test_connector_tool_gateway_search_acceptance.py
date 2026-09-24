from umbod.mcp.connectors.tools.discovery.search import (
    ConnectorToolSearch,
    ConnectorToolSearchCandidate,
    ConnectorToolSearchInput,
    InMemoryFuzzyConnectorToolSearch,
)


def test_search_returns_fuzzy_matches_by_descending_relevance_with_deterministic_ties() -> None:
    search: ConnectorToolSearch = InMemoryFuzzyConnectorToolSearch()
    candidates = [
        _candidate("slack_z_channels", "Slack channels"),
        _candidate("github_channels", "Channels"),
        _candidate("slack_a_channels", "Slack channels"),
    ]

    result = search.search(ConnectorToolSearchInput(query="slack channels", candidates=candidates))

    assert [match.tool_name for match in result.matches] == [
        "slack_a_channels",
        "slack_z_channels",
        "github_channels",
    ]
    assert result.matches[0].relevance_score == result.matches[1].relevance_score
    assert result.matches[1].relevance_score > result.matches[2].relevance_score


def _candidate(tool_name: str, description: str) -> ConnectorToolSearchCandidate:
    return ConnectorToolSearchCandidate(
        tool_name=tool_name,
        description=description,
        connector_id=tool_name.split("_", 1)[0],
        connector_display_name=tool_name.split("_", 1)[0].title(),
        operation_name=tool_name.split("_", 1)[1],
        input_schema={"type": "object", "properties": {}},
    )
