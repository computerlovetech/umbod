import pytest

from umbod.core.callers import AuthenticationProvenance, LegacyGroupClaimPolicy
from umbod.core.callers.membership import (
    UNAVAILABLE_GROUP_MEMBERSHIP,
    GroupMembershipResolver,
    ProviderGroupOverrides,
    ProviderMembershipClaim,
)

_ISSUER = "https://issuer.example/"
_UPSTREAM = AuthenticationProvenance.UPSTREAM_VERIFIED
_CLAIM = ProviderMembershipClaim(_ISSUER, "groups")
_RESOLVER = GroupMembershipResolver(ProviderGroupOverrides(
    _CLAIM,
    {"support": ("customer-ops",), "stale-value": (), "staff": ("readers", "engineers")},
))


@pytest.mark.parametrize("policy", list(LegacyGroupClaimPolicy))
def test_rules_replace_matched_values_without_inheriting_values_with_stale_targets(policy: LegacyGroupClaimPolicy) -> None:
    groups = _RESOLVER.resolve(
        {"iss": _ISSUER, "groups": ["support", "stale-value", "uncatalogued", "staff"]},
        ("groups",), policy, _UPSTREAM,
    )
    assert set(groups.group_ids) == {"customer-ops", "uncatalogued", "readers", "engineers"}
    assert len(groups.group_ids) == 4


@pytest.mark.parametrize("policy", list(LegacyGroupClaimPolicy))
@pytest.mark.parametrize("fields", [("groups", "other"), ("other",)])
def test_other_claim_inherits_without_override(policy: LegacyGroupClaimPolicy, fields: tuple[str, ...]) -> None:
    groups = _RESOLVER.resolve(
        {"iss": _ISSUER, "groups": ["stale-value"], "other": ["stale-value", "support"]},
        fields, policy, _UPSTREAM,
    )
    assert groups.group_ids == ("stale-value", "support")


@pytest.mark.parametrize("issuer", [None, "https://other.example/", _ISSUER.rstrip("/")])
def test_other_or_missing_issuer_keeps_direct_access(issuer: str | None) -> None:
    groups = _RESOLVER.resolve(
        {"iss": issuer, "groups": ["stale-value", "support"], "role": "staff"},
        ("groups",), LegacyGroupClaimPolicy.RUNTIME, _UPSTREAM,
    )
    assert groups.group_ids == ("stale-value", "support")


@pytest.mark.parametrize("provenance", [
    provenance for provenance in AuthenticationProvenance if provenance != _UPSTREAM
])
def test_unverified_callers_keep_legacy_semantics(provenance: AuthenticationProvenance) -> None:
    groups = _RESOLVER.resolve(
        {"iss": _ISSUER, "groups": ["support"], "role": "staff"},
        ("groups",), LegacyGroupClaimPolicy.RUNTIME, provenance,
    )
    assert groups.group_ids == ("support",)


def test_stale_target_suppresses_inheritance_even_inside_a_mixed_legacy_claim() -> None:
    claims = {"iss": _ISSUER, "groups": ["stale-value", 42, "retained"]}
    for policy in (LegacyGroupClaimPolicy.RUNTIME, LegacyGroupClaimPolicy.OPENAPI):
        assert _RESOLVER.resolve(claims, ("groups",), policy, _UPSTREAM).group_ids == ("retained",)
    assert _RESOLVER.resolve(claims, ("groups",), LegacyGroupClaimPolicy.PERSONAL, _UPSTREAM).group_ids == ()


def test_overrides_match_provider_values_and_never_chain_through_internal_group_ids() -> None:
    resolver = GroupMembershipResolver(ProviderGroupOverrides(
        _CLAIM, {"support": ("stale-value",), "stale-value": ()},
    ))
    groups = resolver.resolve(
        {"iss": _ISSUER, "groups": ["support", "stale-value"]},
        ("groups",), LegacyGroupClaimPolicy.RUNTIME, _UPSTREAM,
    )
    assert groups.group_ids == ("stale-value",)


def test_snapshot_read_failure_never_falls_back_for_verified_membership() -> None:
    groups = UNAVAILABLE_GROUP_MEMBERSHIP.resolve(
        {"iss": _ISSUER, "groups": "support"}, ("groups",), LegacyGroupClaimPolicy.RUNTIME, _UPSTREAM,
    )
    assert groups.group_ids == ()
