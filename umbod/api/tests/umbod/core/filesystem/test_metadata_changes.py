import pytest
from pydantic import ValidationError

from umbod.core.filesystem.updates import MetadataChanges
from umbod.core.filesystem.models import UnchangedContentType, UnspecifiedContentType


def test_attribute_changes_preserve_omitted_content_type() -> None:
    changes = MetadataChanges.model_validate({"attributes": {"description": "Read before publishing"}})
    patch = changes.to_core_patch()
    assert patch.attributes == {"description": "Read before publishing"}
    assert isinstance(patch.content_type, UnchangedContentType)


def test_explicit_empty_content_type_clears_without_replacing_attributes() -> None:
    changes = MetadataChanges.model_validate({"content_type": {}})
    patch = changes.to_core_patch()
    assert isinstance(patch.content_type, UnspecifiedContentType)
    assert patch.attributes == {}


@pytest.mark.parametrize("payload", [
    {}, {"attributes": {}}, {"attributes": None}, {"content_type": None},
    {"attributes": {"description": 3}}, {"name": "renamed"}, {"parent_id": "folder"},
])
def test_metadata_changes_reject_empty_null_non_string_and_structural_fields(payload: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        MetadataChanges.model_validate(payload)
