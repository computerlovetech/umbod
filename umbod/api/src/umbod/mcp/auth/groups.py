from collections.abc import Iterable, Mapping, Sequence

from umbod.core.callers import GroupMembership


def capture_runtime_permission_groups(
    claims: Mapping[str, object], claim_fields: Sequence[str]
) -> GroupMembership:
    groups: dict[str, None] = {}
    for field in claim_fields:
        value = claims.get(field)
        if isinstance(value, str):
            groups[value] = None
        elif isinstance(value, Iterable):
            groups.update((group, None) for group in value if isinstance(group, str))
    return GroupMembership(group_ids=tuple(groups))


def capture_openapi_principal_groups(
    claims: Mapping[str, object], claim_name: str
) -> GroupMembership:
    value = claims.get(claim_name)
    if isinstance(value, str):
        return GroupMembership(group_ids=(value,) if value else ())
    if isinstance(value, (list, tuple)):
        groups = tuple(dict.fromkeys(group for group in value if isinstance(group, str) and group))
        return GroupMembership(group_ids=groups)
    return GroupMembership(group_ids=())


def capture_mcp_administrator_groups(
    claims: Mapping[str, object], claim_name: str
) -> GroupMembership:
    value = claims.get(claim_name)
    if isinstance(value, str):
        return GroupMembership(group_ids=(value,))
    if isinstance(value, (list, tuple)):
        return GroupMembership(group_ids=tuple(str(group) for group in value))
    return GroupMembership(group_ids=())
