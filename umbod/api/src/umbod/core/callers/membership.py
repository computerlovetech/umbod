from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum, auto

from .groups import validated_group_claim_values
from .models import GroupMembership


@dataclass(frozen=True)
class ProviderMembershipClaim:
    issuer: str
    claim: str


@dataclass(frozen=True)
class ProviderGroupOverrides:
    provider_claim: ProviderMembershipClaim
    targets_by_value: Mapping[str, tuple[str, ...]]


class MembershipRuleAvailability(Enum):
    NOT_CONFIGURED = auto()
    UNAVAILABLE = auto()


@dataclass(frozen=True)
class GroupMembershipResolver:
    overrides: ProviderGroupOverrides | MembershipRuleAvailability

    def resolve_verified(self, claims: Mapping[str, object]) -> GroupMembership:
        overrides = self.overrides
        if not isinstance(overrides, ProviderGroupOverrides):
            return GroupMembership(group_ids=())
        selector = overrides.provider_claim
        if claims.get("iss") != selector.issuer:
            return GroupMembership(group_ids=())
        values = validated_group_claim_values(claims.get(selector.claim))
        groups = {target for value in values for target in overrides.targets_by_value.get(value, ())}
        return GroupMembership(group_ids=tuple(sorted(groups)))


UNCONFIGURED_GROUP_MEMBERSHIP = GroupMembershipResolver(MembershipRuleAvailability.NOT_CONFIGURED)
UNAVAILABLE_GROUP_MEMBERSHIP = GroupMembershipResolver(MembershipRuleAvailability.UNAVAILABLE)
