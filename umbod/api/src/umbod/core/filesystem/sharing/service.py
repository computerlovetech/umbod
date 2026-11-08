from pydantic import ValidationError

from umbod.core.callers import CallerSnapshot
from umbod.core.identity_directory.user_models import ObservedUserProfile, UserSearchQuery, normalized_name
from umbod.core.identity_directory.users import (
    ObservedUserNotFound, ObservedUserService, UserSearchDenied,
)

from ..authorization import (
    FilesystemIdentityResolver, ObservedUserPrincipalResolver, PermissionDenied, ResolvedIdentity,
    UnresolvedIdentity, allows_resolved,
)
from ..errors import RevisionConflict
from ..models import AccessGrant, NodeId, Permission, Principal, PrincipalType
from .errors import InvalidSharingPolicy, SharingPolicyUnavailable
from .models import (
    EligibleSharingGroup, EligibleSharingGroups, NodePolicyView, NodePolicyState,
    NodeSharingSummaries, NodeSharingSummary, ReplaceNodePolicy,
    RestrictedNodeSharingSummary, ShareableNodeSharingSummary, ShareNodePolicy, ShareNodeResult,
    GroupSharingTarget, GroupSharingRecipient, UserSharingRecipient, SharingRecipient,
    SharingTarget, SharingScope, SharingRecipientSearchQuery, SharingRecipientSearchResult,
)
from .ports import SharingSession, SharingTransactions
from .projection import PolicyProjection, manageable_direct_grant, project_policy


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
            states = {
                node_id: NodePolicyState(
                    node=await session.namespace.get_node(node_id),
                    ownership=await session.access_control.get_owner(node_id),
                    grants=tuple(await session.access_control.list_grants(node_id)),
                    registered_group_ids=frozenset(groups),
                )
                for node_id in unique_ids if node_id in authorized
            }
            profiles = await self._profiles(session, snapshot, tuple(states.values()), False)
            summaries: list[NodeSharingSummary] = []
            for node_id in unique_ids:
                if node_id not in authorized:
                    summaries.append(RestrictedNodeSharingSummary(node_id=node_id, can_share=False))
                    continue
                state = states[node_id]
                projection = project_policy(state, self._issuer, tuple(groups.values()), profiles)
                summaries.append(ShareableNodeSharingSummary(
                    node_id=node_id, can_share=True, grants=projection.grants,
                ))
            return NodeSharingSummaries(nodes=tuple(summaries))

    async def _profiles(
        self, session: SharingSession, snapshot: CallerSnapshot,
        states: tuple[NodePolicyState, ...], require_authority: bool,
    ) -> tuple[ObservedUserProfile, ...]:
        subjects = frozenset(
            grant.principal.id for state in states for grant in state.grants
            if grant.principal.type == PrincipalType.USER
            and grant.principal.issuer == self._issuer and grant.principal.id.strip()
        )
        if not subjects and not require_authority:
            return ()
        try:
            return await ObservedUserService(session.users, self._issuer).profiles(
                snapshot.caller, subjects,
            )
        except UserSearchDenied:
            if require_authority:
                raise PermissionDenied() from None
            return ()

    async def _projection(
        self, session: SharingSession, snapshot: CallerSnapshot,
        state: NodePolicyState, require_user_authority: bool,
    ) -> PolicyProjection:
        profiles = await self._profiles(session, snapshot, (state,), require_user_authority)
        groups = await session.groups.registered_groups()
        return project_policy(state, self._issuer, groups, profiles)

    async def _eligible_groups(
        self, session: SharingSession, state: NodePolicyState,
    ) -> EligibleSharingGroups:
        groups = await session.groups.registered_groups()
        projection = project_policy(state, self._issuer, groups, ())
        blocked = {
            target.group_id for target in projection.blocked
            if isinstance(target, GroupSharingTarget)
        }
        return EligibleSharingGroups(groups=tuple(
            EligibleSharingGroup(
                group_id=group.group_id, label=group.label, description=group.description,
            )
            for group in sorted(groups, key=lambda group: group.group_id)
            if group.group_id.strip() and group.group_id not in blocked
        ))

    async def search_recipients(
        self, snapshot: CallerSnapshot, node_id: NodeId, query: SharingRecipientSearchQuery,
    ) -> SharingRecipientSearchResult:
        identity = await self._identity(snapshot)
        async with self._transactions.transaction() as session:
            state = await self._observe(session, identity, node_id)
            recipients: list[SharingRecipient] = []
            has_more = False
            if "user" in query.scope.recipient_types:
                excluded_subjects = frozenset(
                    grant.principal.id for grant in state.grants
                    if grant.principal.type == PrincipalType.USER
                    and grant.principal.issuer == self._issuer and grant.principal.id.strip()
                    and not manageable_direct_grant(grant)
                )
                try:
                    users = await ObservedUserService(session.users, self._issuer).search(
                        snapshot.caller, UserSearchQuery(
                            query=query.query, limit=50, excluded_subjects=excluded_subjects,
                        ),
                    )
                except UserSearchDenied:
                    raise PermissionDenied() from None
                recipients.extend(
                    UserSharingRecipient(type="user", user_id=user.user_id, label=user.name)
                    for user in users.users
                )
                has_more = users.has_more
            if "group" in query.scope.recipient_types:
                groups = await self._eligible_groups(session, state)
                text = normalized_name(query.query)
                recipients.extend(
                    GroupSharingRecipient(type="group", group_id=group.group_id, label=group.label)
                    for group in groups.groups
                    if text in normalized_name(group.group_id) or text in normalized_name(group.label)
                )
            recipients.sort(key=self._recipient_order)
            return SharingRecipientSearchResult(
                recipients=tuple(recipients[:50]), has_more=has_more or len(recipients) > 50,
            )

    @staticmethod
    def _recipient_order(recipient: SharingRecipient) -> tuple[str, str, str]:
        identifier = recipient.group_id if isinstance(recipient, GroupSharingRecipient) else recipient.user_id
        return recipient.type, normalized_name(recipient.label), identifier

    async def inspect(
        self, snapshot: CallerSnapshot, node_id: NodeId, scope: SharingScope,
    ) -> NodePolicyView:
        identity = await self._identity(snapshot)
        async with self._transactions.transaction() as session:
            state = await self._observe(session, identity, node_id)
            projection = await self._projection(session, snapshot, state, False)
            return projection.view(state, scope)

    def _group_principal(
        self, state: NodePolicyState, target: GroupSharingTarget,
    ) -> Principal:
        principal = Principal(type=PrincipalType.GROUP, issuer=self._issuer, id=target.group_id)
        if target.group_id not in state.registered_group_ids:
            raise InvalidSharingPolicy()
        return principal

    async def _principal(
        self, session: SharingSession, snapshot: CallerSnapshot,
        state: NodePolicyState, target: SharingTarget,
    ) -> Principal:
        if isinstance(target, GroupSharingTarget):
            return self._group_principal(state, target)
        return await self._user_principal(session, snapshot, target.user_id)

    async def share(
        self, snapshot: CallerSnapshot, node_id: NodeId, command: ShareNodePolicy,
    ) -> ShareNodeResult:
        identity = await self._identity(snapshot)
        async with self._transactions.transaction() as session:
            state = await self._observe(session, identity, node_id)
            principal = await self._principal(session, snapshot, state, command.recipient)
            grants = tuple(grant for grant in state.grants if grant.principal == principal)
            if any(not manageable_direct_grant(grant) for grant in grants):
                raise InvalidSharingPolicy()
            current = frozenset(permission for grant in grants for permission in grant.permissions)
            permissions = current | command.permissions
            changed = permissions != current
            if changed:
                await session.grants.upsert(AccessGrant(
                    node_id=node_id, principal=principal,
                    permissions=set(permissions), recursive=False,
                ))
            return ShareNodeResult(
                node_id=node_id, recipient=command.recipient,
                permissions=permissions, changed=changed,
            )

    async def _user_principal(
        self, session: SharingSession, snapshot: CallerSnapshot, user_id: str,
    ) -> Principal:
        users = ObservedUserService(session.users, self._issuer)
        try:
            return await ObservedUserPrincipalResolver(users).resolve(snapshot.caller, user_id)
        except UserSearchDenied:
            raise PermissionDenied() from None
        except (ObservedUserNotFound, ValidationError):
            raise InvalidSharingPolicy() from None

    async def replace(
        self, snapshot: CallerSnapshot, node_id: NodeId, command: ReplaceNodePolicy,
    ) -> NodePolicyView:
        identity = await self._identity(snapshot)
        async with self._transactions.transaction() as session:
            state = await self._observe(session, identity, node_id)
            projection = await self._projection(
                session, snapshot, state, command.recipient_type == "user",
            )
            if command.expected_revision != projection.revision:
                raise RevisionConflict()
            resolved: list[AccessGrant] = []
            for requested in command.grants:
                principal = await self._principal(session, snapshot, state, requested.recipient)
                if any(
                    grant.principal == principal and principal not in projection.editable_principals
                    for grant in state.grants
                ):
                    raise InvalidSharingPolicy()
                resolved.append(AccessGrant(
                    node_id=node_id, principal=principal,
                    permissions=set(requested.permissions), recursive=False,
                ))
            for principal in projection.editable_principals:
                if principal.type.value == command.recipient_type:
                    await session.access_control.remove_grant(node_id, principal)
            for grant in resolved:
                await session.grants.upsert(grant)
            updated = await self._state(session, node_id)
            authoritative = await self._projection(
                session, snapshot, updated, command.recipient_type == "user",
            )
            return authoritative.view(
                updated, SharingScope(recipient_types=frozenset({command.recipient_type})),
            )
