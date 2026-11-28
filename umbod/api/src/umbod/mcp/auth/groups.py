from collections.abc import Mapping

from umbod.core.callers import GroupMembership


def capture_mcp_administrator_groups(
    claims: Mapping[str, object], claim_name: str
) -> GroupMembership:
    value = claims.get(claim_name)
    if isinstance(value, str):
        return GroupMembership(group_ids=(value,))
    if isinstance(value, (list, tuple)):
        return GroupMembership(group_ids=tuple(str(group) for group in value))
    return GroupMembership(group_ids=())
