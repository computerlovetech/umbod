from typing import cast

import pytest

from umbod.core.persistence import (
    AllFields,
    NoFilter,
    Query,
    TableIdentity,
    Unordered,
)


@pytest.mark.parametrize("limit", [True, False, 1.5, "1"])
def test_query_rejects_invalid_limit_types(limit: object) -> None:
    with pytest.raises(TypeError, match="limit must be an integer"):
        Query(NoFilter(), AllFields(), Unordered(), limit=cast(int, limit))


@pytest.mark.parametrize("identifier", ("", "has-dash", "has space", "1starts_with_digit"))
def test_invalid_persistence_identifier_is_rejected(identifier: str) -> None:
    with pytest.raises(ValueError, match="Invalid persistence identifier"):
        TableIdentity(identifier)


def test_neutral_table_identity_accepts_backend_reserved_identifier() -> None:
    assert TableIdentity("sqlite_internal").name == "sqlite_internal"
