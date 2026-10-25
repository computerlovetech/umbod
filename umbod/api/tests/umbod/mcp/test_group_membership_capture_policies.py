from collections.abc import Callable, Mapping

import pytest

from umbod.core.callers import GroupMembership
from umbod.mcp.auth.groups import (
    capture_mcp_administrator_groups,
    capture_openapi_principal_groups,
    capture_runtime_permission_groups,
)


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
    assert capture_runtime_permission_groups({"groups": value}, ("groups",)).group_ids == expected


def test_runtime_capture_unions_only_configured_fields_including_empty_field_name() -> None:
    membership = capture_runtime_permission_groups(
        {"": "blank-field", "groups": ["team", "blank-field"], "roles": "role", "ignored": "other"},
        ("", "groups", "roles", "missing"),
    )
    assert membership.group_ids == ("blank-field", "team", "role")
    assert capture_runtime_permission_groups({"groups": "team"}, ()).group_ids == ()


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
    assert capture_openapi_principal_groups({"groups": value}, "groups").group_ids == expected


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


@pytest.mark.parametrize("capture", [capture_openapi_principal_groups, capture_mcp_administrator_groups])
@pytest.mark.parametrize("claims", [{}, {"other": "team"}])
def test_single_claim_capture_ignores_missing_fields(capture: Callable[[Mapping[str, object], str], GroupMembership], claims: Mapping[str, object]) -> None:
    assert capture(claims, "groups").group_ids == ()
