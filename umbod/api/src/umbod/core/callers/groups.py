from collections.abc import Iterable, Mapping, Sequence
from enum import Enum, auto
from typing import assert_never

from .models import GroupMembership


class LegacyGroupClaimPolicy(Enum):
    RUNTIME = auto()
    OPENAPI = auto()
    PERSONAL = auto()


def resolve_legacy_group_membership(
    claims: Mapping[str, object], claim_fields: Sequence[str], policy: LegacyGroupClaimPolicy,
) -> GroupMembership:
    values = (claims.get(field) for field in claim_fields)
    match policy:
        case LegacyGroupClaimPolicy.RUNTIME:
            return _group_membership_from_values(values)
        case LegacyGroupClaimPolicy.OPENAPI:
            return _group_membership_from_values(_openapi_group_values(value) for value in values)
        case LegacyGroupClaimPolicy.PERSONAL:
            groups = {group for value in values for group in validated_group_claim_values(value)}
            return GroupMembership(group_ids=tuple(sorted(groups)))
    assert_never(policy)


def _openapi_group_values(value: object) -> tuple[str, ...]:
    if isinstance(value, str):
        return (value,) if value else ()
    if isinstance(value, (list, tuple)):
        return tuple(group for group in value if isinstance(group, str) and group)
    return ()


def validated_group_claim_values(value: object) -> tuple[str, ...]:
    if isinstance(value, str):
        return (value,) if value.strip() else ()
    if isinstance(value, (list, tuple)) and all(isinstance(item, str) for item in value):
        return tuple(item for item in value if item.strip())
    return ()


def _group_membership_from_values(values: Iterable[object]) -> GroupMembership:
    groups: dict[str, None] = {}
    for value in values:
        if isinstance(value, str):
            groups[value] = None
        elif isinstance(value, Iterable):
            groups.update((group, None) for group in value if isinstance(group, str))
    return GroupMembership(group_ids=tuple(groups))
