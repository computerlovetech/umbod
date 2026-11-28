from collections.abc import Mapping

import pytest

from umbod.core.callers import LegacyGroupClaimPolicy
from umbod.core.callers.groups import resolve_legacy_group_membership as _legacy_membership
from umbod.mcp.auth.groups import capture_mcp_administrator_groups


@pytest.mark.parametrize("value,expected", [
    ("", ("",)),
    ("  ", ("  ",)),
    (["team", 3, None, "team", ""], ("team", "")),
    (("team", "  "), ("team", "  ")),
    ({"team": False, 7: "ignored"}, ("team",)),
    ({"team"}, ("team",)),
    (iter(["team", False, "team"]), ("team",)),
    ([["team"]], ()),
    (None, ()),
    (42, ()),
])
def test_runtime_capture_retains_only_literal_string_elements(value: object, expected: tuple[str, ...]) -> None:
    assert _legacy_membership({"groups": value}, ("groups",), LegacyGroupClaimPolicy.RUNTIME).group_ids == expected


def test_runtime_capture_unions_only_configured_fields_including_empty_field_name() -> None:
    membership = _legacy_membership(
        {"": "blank-field", "groups": ["team", "blank-field"], "roles": "role", "ignored": "other"},
        ("", "groups", "roles", "missing"),
        LegacyGroupClaimPolicy.RUNTIME,
    )
    assert membership.group_ids == ("blank-field", "team", "role")
    assert _legacy_membership({"groups": "team"}, (), LegacyGroupClaimPolicy.RUNTIME).group_ids == ()


@pytest.mark.parametrize("value,expected", [
    ("", ()),
    ("  ", ("  ",)),
    (["team", 3, None, "team", "", "  "], ("team", "  ")),
    (("team", "team"), ("team",)),
    ({"team": True}, ()),
    ({"team"}, ()),
    (iter(["team"]), ()),
    (None, ()),
    (42, ()),
])
def test_openapi_capture_filters_empty_strings_without_coercion(value: object, expected: tuple[str, ...]) -> None:
    assert _legacy_membership({"groups": value}, ("groups",), LegacyGroupClaimPolicy.OPENAPI).group_ids == expected


@pytest.mark.parametrize("value,expected", [
    ("", ("",)),
    ("  ", ("  ",)),
    (["team", 3, None, "team", ""], ("team", "3", "None", "team", "")),
    ((True, {"nested": "value"}), ("True", "{'nested': 'value'}")),
    ({"team": True}, ()),
    ({"team"}, ()),
    (iter(["team"]), ()),
    (None, ()),
    (42, ()),
])
def test_administrator_capture_preserves_legacy_coercion_order_and_duplicates(value: object, expected: tuple[str, ...]) -> None:
    assert capture_mcp_administrator_groups({"groups": value}, "groups").group_ids == expected


@pytest.mark.parametrize("claims", [{}, {"other": "team"}])
def test_single_claim_capture_ignores_missing_fields(claims: Mapping[str, object]) -> None:
    assert _legacy_membership(claims, ("groups",), LegacyGroupClaimPolicy.OPENAPI).group_ids == ()
    assert capture_mcp_administrator_groups(claims, "groups").group_ids == ()
