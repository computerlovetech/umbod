from umbod.core.filesystem.sharing import (
    GroupPolicy, GroupSharingTarget, NodePolicyView, ShareNodePolicy, SharingScope,
)


GROUP_SCOPE = SharingScope(recipient_types=frozenset({"group"}))


def group_commands(groups: tuple[GroupPolicy, ...]) -> tuple[ShareNodePolicy, ...]:
    return tuple(
        ShareNodePolicy(
            recipient=GroupSharingTarget(type="group", group_id=group.group_id),
            permissions=group.permissions,
        )
        for group in groups
    )


def group_policies(view: NodePolicyView) -> tuple[GroupPolicy, ...]:
    return tuple(
        GroupPolicy(group_id=grant.recipient.group_id, permissions=grant.permissions)
        for grant in view.grants if isinstance(grant.recipient, GroupSharingTarget)
    )


def blocked_groups(view: NodePolicyView) -> tuple[str, ...]:
    return tuple(
        target.group_id for target in view.blocked_recipients
        if isinstance(target, GroupSharingTarget)
    )
