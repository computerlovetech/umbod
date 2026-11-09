import json
from uuid import uuid4

import pytest
from pydantic import ValidationError

from umbod.core.filesystem.updates import NodeChanges, Unchanged
from umbod.mcp.filesystem.update import UpdateNodeCommand


@pytest.mark.parametrize("payload", [
    {}, {"name": None}, {"name": {}}, {"name": 1}, {"parent_id": None},
    {"parent_id": {}}, {"parent_id": "invalid"}, {"metadata": None},
    {"metadata": {}}, {"extra": "value"}, {"path": "/node"}, {"operation": "rename"},
])
def test_node_changes_reject_invalid_wire_values(payload: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        NodeChanges.model_validate_json(json.dumps(payload))


@pytest.mark.parametrize("payload", [
    {"name": "renamed"}, {"parent_id": str(uuid4())}, {"metadata": {"content_type": {}}},
])
def test_node_changes_preserve_omitted_fields(payload: dict[str, object]) -> None:
    patch = NodeChanges.model_validate_json(json.dumps(payload)).to_core_patch()
    for field in ("name", "parent_id", "metadata"):
        assert isinstance(getattr(patch, field), Unchanged) == (field not in payload)


def test_mcp_target_and_revision_do_not_count_as_node_changes() -> None:
    with pytest.raises(ValidationError):
        UpdateNodeCommand.model_validate_json(json.dumps({"node_id": str(uuid4()), "expected_revision": 1}))


def test_wire_schema_excludes_null_and_unchanged_marker() -> None:
    schema = UpdateNodeCommand.model_json_schema()
    assert schema["required"] == ["node_id", "expected_revision"]
    assert schema["properties"]["name"]["type"] == "string"
    assert schema["properties"]["name"]["minLength"] == 1
    assert "UTF-8" in schema["properties"]["name"]["description"]
    assert schema["properties"]["parent_id"]["type"] == "string"
    assert schema["properties"]["parent_id"]["format"] == "uuid"
    assert "Unchanged" not in json.dumps(schema)
    assert '"null"' not in json.dumps(schema)
    assert schema["additionalProperties"] is False
