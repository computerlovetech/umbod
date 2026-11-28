import pytest

from umbod.core.callers import AuthenticationProvenance, LegacyGroupClaimPolicy
from umbod.core.callers.membership import (
    INHERITED_GROUP_MEMBERSHIP,
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
def test_explicit_rules_grant_only_mapped_groups(policy: LegacyGroupClaimPolicy) -> None:
    groups = _RESOLVER.resolve(
        {"iss": _ISSUER, "groups": ["support", "stale-value", "uncatalogued", "staff"]},
        ("groups",), policy, _UPSTREAM,
    )
    assert set(groups.group_ids) == {"customer-ops", "readers", "engineers"}
    assert len(groups.group_ids) == 3


@pytest.mark.parametrize("policy", list(LegacyGroupClaimPolicy))
@pytest.mark.parametrize("fields", [("groups", "other"), ("other",)])
def test_other_claim_never_grants_ordinary_groups(policy: LegacyGroupClaimPolicy, fields: tuple[str, ...]) -> None:
    groups = _RESOLVER.resolve(
        {"iss": _ISSUER, "groups": ["uncatalogued"], "other": ["readers", "support"]},
        fields, policy, _UPSTREAM,
    )
    assert groups.group_ids == ()


@pytest.mark.parametrize("issuer", [None, "https://other.example/", _ISSUER.rstrip("/"), [_ISSUER]])
def test_missing_or_mismatched_issuer_denies_membership(issuer: object) -> None:
    groups = _RESOLVER.resolve(
        {"iss": issuer, "groups": ["stale-value", "support"], "role": "staff"},
        ("groups",), LegacyGroupClaimPolicy.RUNTIME, _UPSTREAM,
    )
    assert groups.group_ids == ()


@pytest.mark.parametrize("provenance", [
    provenance for provenance in AuthenticationProvenance if provenance != _UPSTREAM
])
def test_unverified_callers_keep_legacy_semantics(provenance: AuthenticationProvenance) -> None:
    groups = _RESOLVER.resolve(
        {"iss": _ISSUER, "groups": ["support"], "role": "staff"},
        ("groups",), LegacyGroupClaimPolicy.RUNTIME, provenance,
    )
    assert groups.group_ids == ("support",)


@pytest.mark.parametrize("policy", list(LegacyGroupClaimPolicy))
@pytest.mark.parametrize("value", [["support", 42], {"support": True}, 42, None])
def test_malformed_verified_claim_never_partially_grants_membership(
    policy: LegacyGroupClaimPolicy, value: object,
) -> None:
    claims = {"iss": _ISSUER, "groups": value}
    assert _RESOLVER.resolve(claims, ("groups",), policy, _UPSTREAM).group_ids == ()


def test_overrides_match_provider_values_and_never_chain_through_internal_group_ids() -> None:
    resolver = GroupMembershipResolver(ProviderGroupOverrides(
        _CLAIM, {"support": ("stale-value",), "stale-value": ()},
    ))
    groups = resolver.resolve(
        {"iss": _ISSUER, "groups": ["support", "stale-value"]},
        ("groups",), LegacyGroupClaimPolicy.RUNTIME, _UPSTREAM,
    )
    assert groups.group_ids == ("stale-value",)


@pytest.mark.parametrize(
    "resolver", [INHERITED_GROUP_MEMBERSHIP, UNAVAILABLE_GROUP_MEMBERSHIP]
)
def test_missing_or_unavailable_mappings_deny_verified_membership(resolver: GroupMembershipResolver) -> None:
    groups = resolver.resolve(
        {"iss": _ISSUER, "groups": "support"}, ("groups",), LegacyGroupClaimPolicy.RUNTIME, _UPSTREAM,
    )
    assert groups.group_ids == ()
