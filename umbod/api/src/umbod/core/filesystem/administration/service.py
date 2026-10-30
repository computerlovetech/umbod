import hashlib
import json

from ..models import (
    SYSTEM_ROOT_OWNER, AccessGrant, EmptyContent, NodeKind, Principal,
    PrincipalType, RootParent,
)
from ..namespace import ROOT_ID
from ..group_policy import canonical_grants, editable_grant
from .errors import PolicyConflict, PolicyRevisionConflict, PolicyUnavailable
from .models import (
    GroupPolicy, RootGroupPolicyView, RootPolicyState,
    RootPolicyStatus, SaveRootGroupPolicy,
)
from .ports import RootPolicyTransactions


def policy_status(state: RootPolicyState) -> RootPolicyStatus:
    if state.malformed_root:
        return RootPolicyStatus.CONFLICT
    if state.roots:
        root = state.roots[0]
        if (
            root.id != ROOT_ID or root.name != ""
            or root.kind != NodeKind.DIRECTORY
            or not isinstance(root.parent_id, RootParent)
            or not isinstance(root.content, EmptyContent)
        ):
            return RootPolicyStatus.CONFLICT
    if state.owners:
        if not state.roots or state.owners[0].owner != SYSTEM_ROOT_OWNER:
            return RootPolicyStatus.CONFLICT
        return RootPolicyStatus.READY
    if state.grants or state.has_children:
        return RootPolicyStatus.CONFLICT
    return RootPolicyStatus.UNINITIALIZED


def revision(state: RootPolicyState, issuer: str) -> str:
    payload = state.model_dump(mode="json", exclude={"grants", "has_children"})
    payload["managed_issuer"] = issuer
    if policy_status(state) != RootPolicyStatus.READY:
        payload["has_children"] = state.has_children
    payload["grants"] = canonical_grants(state.grants)
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def policy_view(state: RootPolicyState, issuer: str) -> RootGroupPolicyView:
    blocked = {
        grant.principal.id for grant in state.grants
        if grant.principal.type == PrincipalType.GROUP
        and grant.principal.issuer == issuer
        and grant.principal.id.strip()
        and not editable_grant(grant, issuer)
    }
    groups = tuple(
        GroupPolicy(group_id=grant.principal.id, permissions=frozenset(grant.permissions))
        for grant in state.grants
        if editable_grant(grant, issuer) and grant.principal.id not in blocked
    )
    return RootGroupPolicyView(
        status=policy_status(state), revision=revision(state, issuer),
        groups=tuple(sorted(groups, key=lambda group: group.group_id)),
        blocked_group_ids=tuple(sorted(blocked)),
    )


class RootGroupPolicyService:
    def __init__(self, transactions: RootPolicyTransactions, issuer: str) -> None:
        if not isinstance(issuer, str) or not issuer.strip():
            raise PolicyUnavailable()
        self._transactions = transactions
        self._issuer = issuer

    async def inspect(self) -> RootGroupPolicyView:
        async with self._transactions.read() as session:
            return policy_view(await session.observe(), self._issuer)

    async def save(self, command: SaveRootGroupPolicy) -> RootGroupPolicyView:
        async with self._transactions.write() as session:
            state = await session.observe()
            view = policy_view(state, self._issuer)
            if command.expected_revision != view.revision:
                raise PolicyRevisionConflict()
            if view.status == RootPolicyStatus.CONFLICT:
                raise PolicyConflict()
            if set(view.blocked_group_ids).intersection(group.group_id for group in command.groups):
                raise PolicyConflict()
            if view.status == RootPolicyStatus.UNINITIALIZED:
                await session.ensure_root()
            for grant in state.grants:
                if editable_grant(grant, self._issuer) and grant.principal.id not in view.blocked_group_ids:
                    await session.remove_group(grant.principal)
            for group in command.groups:
                await session.add_group(AccessGrant(
                    node_id=ROOT_ID,
                    principal=Principal(type=PrincipalType.GROUP, issuer=self._issuer, id=group.group_id),
                    permissions=set(group.permissions), recursive=False,
                ))
            result = policy_view(await session.observe(), self._issuer)
        return result
