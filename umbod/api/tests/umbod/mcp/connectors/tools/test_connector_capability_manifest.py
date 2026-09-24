from umbod.mcp.connectors.tools.discovery.manifest import (
    ConnectorCapabilityManifestFormatter,
    ConnectorCapabilityManifestService,
)
from umbod.mcp.connectors.tools.discovery.search import ConnectorToolSearchCandidate


def _candidate(
    connector_id: str,
    display_name: str,
    operation_name: str,
    capability_description: str = "Manage collaboration goals",
) -> ConnectorToolSearchCandidate:
    return ConnectorToolSearchCandidate(
        tool_name=f"{connector_id}_{operation_name}",
        description=f"secret description for {operation_name}",
        connector_id=connector_id,
        connector_display_name=display_name,
        connector_capability_description=capability_description,
        operation_name=operation_name,
        input_schema={"properties": {"credential": {"type": "string"}}},
    )


def test_manifest_groups_and_counts_eligible_candidates_deterministically() -> None:
    manifest = ConnectorCapabilityManifestService().derive(
        [
            _candidate("z", "Zulu", "second"),
            _candidate("a", "Alpha", "only"),
            _candidate("z", "Zulu", "first"),
        ]
    )

    assert [
        (domain.connector_id, domain.display_name, domain.operation_count)
        for domain in manifest.domains
    ] == [
        ("a", "Alpha", 1),
        ("z", "Zulu", 2),
    ]


def test_manifest_empty_when_candidate_path_is_empty() -> None:
    manifest = ConnectorCapabilityManifestService().derive([])

    assert manifest.domains == ()


def test_formatter_is_bounded_and_does_not_leak_deferred_details() -> None:
    candidate = _candidate("slack", "Slack", "list_private_channels")
    manifest = ConnectorCapabilityManifestService().derive([candidate])

    description = ConnectorCapabilityManifestFormatter(character_budget=120).format(
        "Search accessible tools.", manifest
    )

    assert len(description) <= 120
    assert "Slack: Manage collaboration goals (1 operations)" in description
    assert "list_private_channels" not in description
    assert "credential" not in description
    assert "secret description" not in description


def test_manifest_rejects_conflicting_descriptions_for_same_connector_id() -> None:
    candidates = [
        _candidate("slack", "Slack", "first", "Manage messages"),
        _candidate("slack", "Slack", "second", "Manage channels"),
    ]

    try:
        ConnectorCapabilityManifestService().derive(candidates)
    except ValueError as error:
        assert "slack" in str(error)
    else:
        raise AssertionError("conflicting connector metadata was accepted")


def test_formatter_omits_domains_that_do_not_fit_budget() -> None:
    candidates = [_candidate(str(index), f"Domain {index}", "operation") for index in range(20)]
    manifest = ConnectorCapabilityManifestService().derive(candidates)

    description = ConnectorCapabilityManifestFormatter(character_budget=70).format(
        "Search accessible tools.", manifest
    )

    assert len(description) <= 70
    assert description == ConnectorCapabilityManifestFormatter(character_budget=70).format(
        "Search accessible tools.", manifest
    )
