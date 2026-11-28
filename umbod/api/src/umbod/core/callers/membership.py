from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum, auto
from typing import Protocol

from .groups import (
    LegacyGroupClaimPolicy,
    resolve_legacy_group_membership,
    validated_group_claim_values,
)
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
        if not isinstance(overrides, ProviderGroupOverrides):
            return GroupMembership(group_ids=())
        selector = overrides.provider_claim
        if claims.get("iss") != selector.issuer or selector.claim not in claim_fields:
            return GroupMembership(group_ids=())
        values = validated_group_claim_values(claims.get(selector.claim))
        groups = dict.fromkeys(
            target for value in values for target in overrides.targets_by_value.get(value, ())
        )
        return GroupMembership(
            group_ids=tuple(sorted(groups)) if policy is LegacyGroupClaimPolicy.PERSONAL else tuple(groups)
        )


INHERITED_GROUP_MEMBERSHIP = GroupMembershipResolver(MembershipRuleAvailability.INHERITED)
UNAVAILABLE_GROUP_MEMBERSHIP = GroupMembershipResolver(MembershipRuleAvailability.UNAVAILABLE)
