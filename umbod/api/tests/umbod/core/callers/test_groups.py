from collections.abc import Iterable

import pytest

from umbod.core.callers import GroupMembership, LegacyGroupClaimPolicy
from umbod.core.callers.groups import resolve_legacy_group_membership


def _runtime_membership(values: Iterable[object]) -> GroupMembership:
    claims = {str(index): value for index, value in enumerate(values)}
    return resolve_legacy_group_membership(claims, tuple(claims), LegacyGroupClaimPolicy.RUNTIME)


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
    assert _runtime_membership(values) == GroupMembership(group_ids=expected)


def test_runtime_group_projection_accepts_one_pass_iterables_and_detaches_results() -> None:
    source: list[object] = ["team", 3, "other"]
    observations: Iterable[object] = iter((iter(source), "team"))
    result = _runtime_membership(observations)
    source.clear()
    assert result.group_ids == ("team", "other")


def test_runtime_group_projection_has_no_cross_operation_membership_cache() -> None:
    assert _runtime_membership(("team",)).group_ids == ("team",)
    assert _runtime_membership(("other",)).group_ids == ("other",)
    assert _runtime_membership(()).group_ids == ()
