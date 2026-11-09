import hashlib
import json
from dataclasses import dataclass

from umbod.core.groups.models import Group
from umbod.core.identity_directory.user_models import ObservedUserProfile

from ..group_policy import canonical_grants
from ..models import AccessGrant, Principal, PrincipalType, Permission
from .models import (
    GroupSharingRecipient, GroupSharingTarget, NodePolicyState, NodePolicyView,
    SharingGrantSummary, SharingRecipient, SharingScope, SharingTarget, UserSharingRecipient, UserSharingTarget,
)


def manageable_direct_grant(grant: AccessGrant) -> bool:
    return (
        isinstance(grant.recursive, bool)
        and bool(grant.permissions)
        and all(isinstance(permission, Permission) for permission in grant.permissions)
    )


@dataclass(frozen=True)
class PolicyProjection:
    grants: tuple[SharingGrantSummary, ...]
    blocked: tuple[SharingTarget, ...]
    editable_principals: frozenset[Principal]
    revision: str

    def view(self, state: NodePolicyState, scope: SharingScope) -> NodePolicyView:
        return NodePolicyView(
            node_id=state.node.id, revision=self.revision,
            grants=tuple(grant for grant in self.grants if grant.recipient.type in scope.recipient_types),
            blocked_recipients=tuple(target for target in self.blocked if target.type in scope.recipient_types),
        )


def project_policy(
    state: NodePolicyState, issuer: str, groups: tuple[Group, ...],
    profiles: tuple[ObservedUserProfile, ...],
) -> PolicyProjection:
    recipients: dict[Principal, SharingRecipient] = {
        Principal(type=PrincipalType.GROUP, issuer=issuer, id=group.group_id):
        GroupSharingRecipient(type="group", group_id=group.group_id, label=group.label)
        for group in groups if group.group_id.strip()
    }
    recipients.update({
        Principal(type=PrincipalType.USER, issuer=issuer, id=profile.subject):
        UserSharingRecipient(type="user", user_id=profile.user_id, label=profile.name)
        for profile in profiles if profile.issuer == issuer and profile.subject.strip()
    })
    eligible = frozenset(
        grant.principal for grant in state.grants
        if grant.principal in recipients and manageable_direct_grant(grant)
    )
    protected = frozenset(
        grant.principal for grant in state.grants
        if grant.principal not in recipients or not manageable_direct_grant(grant)
    )
    editable = eligible - protected
    blocked: list[SharingTarget] = []
    for principal in sorted(protected, key=lambda value: (value.type, value.id)):
        if principal.issuer != issuer:
            continue
        if principal.type == PrincipalType.GROUP and principal.id.strip():
            blocked.append(GroupSharingTarget(type="group", group_id=principal.id))
        elif principal.type == PrincipalType.USER and principal in recipients:
            blocked.append(UserSharingTarget(type="user", user_id=recipients[principal].user_id))
    grants = tuple(sorted(
        (
            SharingGrantSummary(recipient=recipients[grant.principal], permissions=frozenset(grant.permissions), recursive=grant.recursive)
            for grant in state.grants if grant.principal in editable
        ),
        key=lambda grant: (
            grant.recipient.type,
            grant.recipient.group_id if isinstance(grant.recipient, GroupSharingRecipient) else grant.recipient.user_id,
        ),
    ))
    payload = {
        "node": state.node.model_dump(mode="json"),
        "ownership": state.ownership.model_dump(mode="json"),
        "grants": canonical_grants(state.grants),
        "managed_issuer": issuer,
        "editable_group_ids": sorted(principal.id for principal in editable if principal.type == PrincipalType.GROUP),
        "user_bindings": sorted(
            (principal.id, recipient.user_id, principal in editable)
            for principal, recipient in recipients.items()
            if isinstance(recipient, UserSharingRecipient)
            and any(grant.principal == principal for grant in state.grants)
        ),
    }
    revision = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return PolicyProjection(grants=grants, blocked=tuple(blocked), editable_principals=editable, revision=revision)
