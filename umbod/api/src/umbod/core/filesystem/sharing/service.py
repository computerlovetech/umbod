import hashlib
import json

from umbod.core.callers import CallerSnapshot

from ..authorization import (
    FilesystemIdentityResolver, PermissionDenied, ResolvedIdentity,
    UnresolvedIdentity, allows_resolved,
)
from ..errors import RevisionConflict
from ..group_policy import GroupPolicy, canonical_grants, editable_grant
from ..models import AccessGrant, NodeId, Permission, Principal, PrincipalType
from .errors import InvalidSharingPolicy, SharingPolicyUnavailable
from .models import (
    EligibleSharingGroup, EligibleSharingGroups, NodeGroupPolicyView, NodePolicyState,
    GroupSharingRecipient, NodeSharingSummaries, NodeSharingSummary, ReplaceNodeGroupPolicy,
    RestrictedNodeSharingSummary, ShareableNodeSharingSummary, ShareNodeGroupResult, SharingGrantSummary,
)
from .ports import SharingSession, SharingTransactions


def managed_grant(grant: AccessGrant, issuer: str, registered: frozenset[str]) -> bool:
    return editable_grant(grant, issuer) and grant.principal.id in registered


def policy_view(state: NodePolicyState, issuer: str) -> NodeGroupPolicyView:
    eligible = frozenset(
        grant.principal.id for grant in state.grants
        if managed_grant(grant, issuer, state.registered_group_ids)
    )
    blocked = {
        grant.principal.id for grant in state.grants
        if grant.principal.type == PrincipalType.GROUP
        and grant.principal.issuer == issuer
        and grant.principal.id.strip()
        and not managed_grant(grant, issuer, state.registered_group_ids)
    }
    payload = {
        "node": state.node.model_dump(mode="json"),
        "ownership": state.ownership.model_dump(mode="json"),
        "grants": canonical_grants(state.grants),
        "managed_issuer": issuer,
        "editable_group_ids": sorted(eligible),
    }
    revision = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return NodeGroupPolicyView(
        node_id=state.node.id,
        revision=revision,
        groups=tuple(sorted(
            (
                GroupPolicy(group_id=grant.principal.id, permissions=frozenset(grant.permissions))
                for grant in state.grants
                if managed_grant(grant, issuer, state.registered_group_ids)
                and grant.principal.id not in blocked
            ),
            key=lambda group: group.group_id,
        )),
        blocked_group_ids=tuple(sorted(blocked)),
    )


class SharingService:
    def __init__(
        self, resolver: FilesystemIdentityResolver, transactions: SharingTransactions, issuer: str,
    ) -> None:
        if not isinstance(issuer, str) or not issuer.strip():
            raise SharingPolicyUnavailable()
        self._resolver = resolver
        self._transactions = transactions
        self._issuer = issuer

    async def _identity(self, snapshot: CallerSnapshot) -> ResolvedIdentity:
        identity = await self._resolver.resolve(snapshot)
        if isinstance(identity, UnresolvedIdentity):
            raise PermissionDenied()
        return identity

    async def _can_share(
        self, session: SharingSession, identity: ResolvedIdentity, node_id: NodeId,
    ) -> bool:
        for permission in (Permission.DISCOVER, Permission.SHARE):
            if not await allows_resolved(
                identity, node_id, permission, session.namespace, session.access_control,
            ):
                return False
        return True

    async def _observe(
        self, session: SharingSession, identity: ResolvedIdentity, node_id: NodeId,
    ) -> NodePolicyState:
        if not await self._can_share(session, identity, node_id):
            raise PermissionDenied()
        return await self._state(session, node_id)

    async def _state(self, session: SharingSession, node_id: NodeId) -> NodePolicyState:
        return NodePolicyState(
            node=await session.namespace.get_node(node_id),
            ownership=await session.access_control.get_owner(node_id),
            grants=tuple(await session.access_control.list_grants(node_id)),
            registered_group_ids=await session.groups.registered_group_ids(),
        )

    async def summarize_nodes(
        self, snapshot: CallerSnapshot, node_ids: tuple[NodeId, ...],
    ) -> NodeSharingSummaries:
        identity = await self._identity(snapshot)
        unique_ids = tuple(dict.fromkeys(node_ids))
        if not unique_ids:
            return NodeSharingSummaries(nodes=())
        async with self._transactions.transaction() as session:
            authorized: set[NodeId] = set()
            for node_id in unique_ids:
                if await self._can_share(session, identity, node_id):
                    authorized.add(node_id)
            groups = {
                group.group_id: group
                for group in await session.groups.registered_groups()
            } if authorized else {}
            summaries: list[NodeSharingSummary] = []
            for node_id in unique_ids:
                if node_id not in authorized:
                    summaries.append(RestrictedNodeSharingSummary(node_id=node_id, can_share=False))
                    continue
                state = NodePolicyState(
                    node=await session.namespace.get_node(node_id),
                    ownership=await session.access_control.get_owner(node_id),
                    grants=tuple(await session.access_control.list_grants(node_id)),
                    registered_group_ids=frozenset(groups),
                )
                view = policy_view(state, self._issuer)
                summaries.append(ShareableNodeSharingSummary(
                    node_id=node_id, can_share=True,
                    grants=tuple(
                        SharingGrantSummary(
                            recipient=GroupSharingRecipient(
                                type="group", group_id=grant.group_id,
                                label=groups[grant.group_id].label,
                            ),
                            permissions=grant.permissions,
                        )
                        for grant in view.groups
                    ),
                ))
            return NodeSharingSummaries(nodes=tuple(summaries))

    async def eligible_groups(self, snapshot: CallerSnapshot, node_id: NodeId) -> EligibleSharingGroups:
        identity = await self._identity(snapshot)
        async with self._transactions.transaction() as session:
            view = policy_view(await self._observe(session, identity, node_id), self._issuer)
            groups = await session.groups.registered_groups()
            return EligibleSharingGroups(groups=tuple(
                EligibleSharingGroup(
                    group_id=group.group_id, label=group.label, description=group.description,
                )
                for group in sorted(groups, key=lambda group: group.group_id)
                if group.group_id.strip() and group.group_id not in view.blocked_group_ids
            ))

    async def inspect(self, snapshot: CallerSnapshot, node_id: NodeId) -> NodeGroupPolicyView:
        identity = await self._identity(snapshot)
        async with self._transactions.transaction() as session:
            return policy_view(await self._observe(session, identity, node_id), self._issuer)

    async def share(
        self, snapshot: CallerSnapshot, node_id: NodeId, command: GroupPolicy,
    ) -> ShareNodeGroupResult:
        identity = await self._identity(snapshot)
        async with self._transactions.transaction() as session:
            state = await self._observe(session, identity, node_id)
            view = policy_view(state, self._issuer)
            if (
                command.group_id not in state.registered_group_ids
                or command.group_id in view.blocked_group_ids
            ):
                raise InvalidSharingPolicy()
            current = frozenset(
                permission for group in view.groups if group.group_id == command.group_id
                for permission in group.permissions
            )
            permissions = current | command.permissions
            changed = permissions != current
            if changed:
                await session.grants.upsert(AccessGrant(
                    node_id=node_id,
                    principal=Principal(
                        type=PrincipalType.GROUP, issuer=self._issuer, id=command.group_id,
                    ),
                    permissions=set(permissions), recursive=False,
                ))
            return ShareNodeGroupResult(
                node_id=node_id, group_id=command.group_id,
                permissions=permissions, changed=changed,
            )

    async def replace(
        self, snapshot: CallerSnapshot, node_id: NodeId, command: ReplaceNodeGroupPolicy,
    ) -> NodeGroupPolicyView:
        identity = await self._identity(snapshot)
        async with self._transactions.transaction() as session:
            state = await self._observe(session, identity, node_id)
            view = policy_view(state, self._issuer)
            if command.expected_revision != view.revision:
                raise RevisionConflict()
            recipients = {group.group_id for group in command.groups}
            if (
                not recipients.issubset(state.registered_group_ids)
                or recipients.intersection(view.blocked_group_ids)
            ):
                raise InvalidSharingPolicy()
            for grant in state.grants:
                if (
                    managed_grant(grant, self._issuer, state.registered_group_ids)
                    and grant.principal.id not in view.blocked_group_ids
                ):
                    await session.access_control.remove_grant(node_id, grant.principal)
            for group in command.groups:
                await session.grants.upsert(AccessGrant(
                    node_id=node_id,
                    principal=Principal(
                        type=PrincipalType.GROUP, issuer=self._issuer, id=group.group_id,
                    ),
                    permissions=set(group.permissions), recursive=False,
                ))
            return policy_view(await self._state(session, node_id), self._issuer)
