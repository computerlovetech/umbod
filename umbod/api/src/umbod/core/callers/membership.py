from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum, auto
from typing import Protocol

from .groups import LegacyGroupClaimPolicy, resolve_legacy_group_membership
from .models import AuthenticationProvenance, GroupMembership


@dataclass(frozen=True)
class ProviderMembershipClaim:
    issuer: str
    claim: str


@dataclass(frozen=True)
class ProviderGroupOverrides:
    provider_claim: ProviderMembershipClaim
    targets_by_value: Mapping[str, tuple[str, ...]]


class GroupMembershipResolution(Protocol):
    def resolve(
        self,
        claims: Mapping[str, object],
        claim_fields: Sequence[str],
        policy: LegacyGroupClaimPolicy,
        authentication: AuthenticationProvenance,
    ) -> GroupMembership: ...


class MembershipRuleAvailability(Enum):
    INHERITED = auto()
    UNAVAILABLE = auto()


@dataclass(frozen=True)
class GroupMembershipResolver:
    overrides: ProviderGroupOverrides | MembershipRuleAvailability

    def resolve(
        self,
        claims: Mapping[str, object],
        claim_fields: Sequence[str],
        policy: LegacyGroupClaimPolicy,
        authentication: AuthenticationProvenance,
    ) -> GroupMembership:
        if authentication != AuthenticationProvenance.UPSTREAM_VERIFIED:
            return resolve_legacy_group_membership(claims, claim_fields, policy)
        overrides = self.overrides
        if overrides is MembershipRuleAvailability.UNAVAILABLE:
            return GroupMembership(group_ids=())
        if isinstance(overrides, ProviderGroupOverrides) and (
            claims.get("iss") == overrides.provider_claim.issuer
            and overrides.provider_claim.claim in claim_fields
        ):
            return _resolve_with_overrides(claims, claim_fields, policy, overrides)
        return resolve_legacy_group_membership(claims, claim_fields, policy)


def _resolve_with_overrides(
    claims: Mapping[str, object],
    claim_fields: Sequence[str],
    policy: LegacyGroupClaimPolicy,
    overrides: ProviderGroupOverrides,
) -> GroupMembership:
    resolved: dict[str, None] = {}
    for field in claim_fields:
        groups = resolve_legacy_group_membership(claims, (field,), policy).group_ids
        for group_id in groups:
            targets = (
                overrides.targets_by_value.get(group_id, (group_id,))
                if field == overrides.provider_claim.claim
                else (group_id,)
            )
            resolved.update(dict.fromkeys(targets))
    groups = tuple(resolved)
    return GroupMembership(
        group_ids=tuple(sorted(groups)) if policy is LegacyGroupClaimPolicy.PERSONAL else groups
    )


INHERITED_GROUP_MEMBERSHIP = GroupMembershipResolver(MembershipRuleAvailability.INHERITED)
UNAVAILABLE_GROUP_MEMBERSHIP = GroupMembershipResolver(MembershipRuleAvailability.UNAVAILABLE)
