from collections.abc import Iterable

import pytest

from umbod.core.callers import GroupMembership, group_membership_from_values


@pytest.mark.parametrize("values,expected", [
    ((), ()),
    ((None, 123, True), ()),
    (("team", "team", "other"), ("team", "other")),
    ((["team", None, 123, "other"], ("team", "last")), ("team", "other", "last")),
    (({"team": False, "other": True},), ("team", "other")),
    ((b"team",), ()),
    (("", ["team", "", " Team "]), ("", "team", " Team ")),
])
def test_runtime_group_projection_preserves_existing_exact_semantics(
    values: tuple[object, ...], expected: tuple[str, ...],
) -> None:
    assert group_membership_from_values(values) == GroupMembership(group_ids=expected)


def test_runtime_group_projection_accepts_one_pass_iterables_and_detaches_results() -> None:
    source: list[object] = ["team", 3, "other"]
    observations: Iterable[object] = iter((iter(source), "team"))
    result = group_membership_from_values(observations)
    source.clear()
    assert result.group_ids == ("team", "other")


def test_runtime_group_projection_has_no_cross_operation_membership_cache() -> None:
    assert group_membership_from_values(("team",)).group_ids == ("team",)
    assert group_membership_from_values(("other",)).group_ids == ("other",)
    assert group_membership_from_values(()).group_ids == ()
