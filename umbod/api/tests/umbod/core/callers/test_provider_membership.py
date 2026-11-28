import pytest

from umbod.core.callers import GroupMembership
from umbod.core.callers.membership import (
    UNCONFIGURED_GROUP_MEMBERSHIP,
    UNAVAILABLE_GROUP_MEMBERSHIP,
    GroupMembershipResolver,
    ProviderGroupOverrides,
    ProviderMembershipClaim,
)

_ISSUER = "https://issuer.example/"
_CLAIM = ProviderMembershipClaim(_ISSUER, "groups")
_RESOLVER = GroupMembershipResolver(ProviderGroupOverrides(
    _CLAIM,
    {"support": ("customer-ops", "readers"), "stale-value": (), "staff": ("readers", "engineers")},
))


def test_verified_membership_contains_only_unique_sorted_umbod_group_ids() -> None:
    groups = _RESOLVER.resolve_verified({
        "iss": _ISSUER, "groups": ["staff", "stale-value", "uncatalogued", "support"],
    })
    assert groups == GroupMembership(group_ids=("customer-ops", "engineers", "readers"))


def test_different_provider_selectors_produce_the_same_membership_format() -> None:
    other_issuer = "https://second.example/"
    second = GroupMembershipResolver(ProviderGroupOverrides(
        ProviderMembershipClaim(other_issuer, "roles"), {"agent": ("customer-ops", "readers")},
    ))
    assert _RESOLVER.resolve_verified({"iss": _ISSUER, "groups": "support"}) == second.resolve_verified({
        "iss": other_issuer, "roles": ["agent"],
    }) == GroupMembership(group_ids=("customer-ops", "readers"))


def test_other_claim_never_grants_ordinary_groups() -> None:
    groups = _RESOLVER.resolve_verified({
        "iss": _ISSUER, "groups": ["uncatalogued"], "other": ["readers", "support"],
    })
    assert groups.group_ids == ()


@pytest.mark.parametrize("issuer", [None, "https://other.example/", _ISSUER.rstrip("/"), [_ISSUER]])
def test_missing_or_mismatched_issuer_denies_membership(issuer: object) -> None:
    groups = _RESOLVER.resolve_verified({
        "iss": issuer, "groups": ["stale-value", "support"], "role": "staff",
    })
    assert groups.group_ids == ()


@pytest.mark.parametrize("value", [["support", 42], {"support": True}, 42, None])
def test_malformed_verified_claim_never_partially_grants_membership(value: object) -> None:
    assert _RESOLVER.resolve_verified({"iss": _ISSUER, "groups": value}).group_ids == ()


def test_overrides_match_provider_values_and_never_chain_through_internal_group_ids() -> None:
    resolver = GroupMembershipResolver(ProviderGroupOverrides(
        _CLAIM, {"support": ("stale-value",), "stale-value": ()},
    ))
    groups = resolver.resolve_verified({"iss": _ISSUER, "groups": ["support", "stale-value"]})
    assert groups.group_ids == ("stale-value",)


@pytest.mark.parametrize("resolver", [UNCONFIGURED_GROUP_MEMBERSHIP, UNAVAILABLE_GROUP_MEMBERSHIP])
def test_missing_or_unavailable_mappings_deny_verified_membership(resolver: GroupMembershipResolver) -> None:
    assert resolver.resolve_verified({"iss": _ISSUER, "groups": "support"}).group_ids == ()
