from uuid import uuid4

import pytest
from pydantic import ValidationError

from umbod.core.filesystem import Permission
from umbod.core.filesystem.sharing import (
    GroupSharingRecipient, NodeSharingSummaries, RestrictedNodeSharingSummary,
    ShareableNodeSharingSummary, SharingGrantSummary,
)


@pytest.mark.parametrize("identifier", [" Team ", "Team", "team", "a/b"])
def test_summary_recipient_preserves_exact_identifier(identifier: str) -> None:
    recipient = GroupSharingRecipient(type="group", group_id=identifier, label="Current label")
    assert recipient.group_id == identifier
    with pytest.raises(ValidationError):
        recipient.label = "changed"


@pytest.mark.parametrize("payload", [
    {"type": "user", "group_id": "team", "label": "Team"},
    {"type": "group", "group_id": " \t", "label": "Team"},
    {"type": "group", "group_id": "team"},
    {"type": "group", "group_id": "team", "label": "Team", "issuer": "secret"},
])
def test_summary_recipient_rejects_invalid_input(payload: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        GroupSharingRecipient.model_validate(payload)


def test_summary_grant_rejects_empty_permissions() -> None:
    with pytest.raises(ValidationError):
        SharingGrantSummary(
            recipient=GroupSharingRecipient(type="group", group_id="team", label="Team"),
            permissions=frozenset(),
        )


def test_summary_serialization_sorts_permissions_and_omits_restricted_grants() -> None:
    node_id = uuid4()
    grant = SharingGrantSummary(
        recipient=GroupSharingRecipient(type="group", group_id="team", label="Team"),
        permissions=frozenset(Permission),
    )
    result = NodeSharingSummaries(nodes=(
        ShareableNodeSharingSummary(node_id=node_id, can_share=True, grants=(grant,)),
        RestrictedNodeSharingSummary(node_id=node_id, can_share=False),
    ))
    payload = result.model_dump(mode="json")
    assert payload["nodes"][0]["grants"][0]["permissions"] == sorted(value.value for value in Permission)
    assert payload["nodes"][1] == {"node_id": str(node_id), "can_share": False}
    assert NodeSharingSummaries.model_validate_json(result.model_dump_json()) == result
    schema = NodeSharingSummaries.model_json_schema()
    restricted = schema["$defs"]["RestrictedNodeSharingSummary"]
    assert set(restricted["properties"]) == {"node_id", "can_share"}
    assert restricted["additionalProperties"] is False
    assert schema["properties"]["nodes"]["items"]["discriminator"]["propertyName"] == "can_share"
    for definition in schema["$defs"].values():
        if "properties" in definition:
            assert set(definition["required"]) == set(definition["properties"])


@pytest.mark.parametrize("payload", [
    {"can_share": False, "grants": []},
    {"can_share": True},
    {"can_share": "false"},
    {},
])
def test_summary_union_rejects_invalid_variants(payload: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        NodeSharingSummaries.model_validate({"nodes": [{"node_id": uuid4(), **payload}]})
