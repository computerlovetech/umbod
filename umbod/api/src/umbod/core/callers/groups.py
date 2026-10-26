from collections.abc import Iterable

from .models import GroupMembership


def group_membership_from_values(values: Iterable[object]) -> GroupMembership:
    groups: dict[str, None] = {}
    for value in values:
        if isinstance(value, str):
            groups[value] = None
        elif isinstance(value, Iterable):
            groups.update((group, None) for group in value if isinstance(group, str))
    return GroupMembership(group_ids=tuple(groups))
