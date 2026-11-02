from collections.abc import Sequence

from umbod.core.callers import CallerSnapshot

from ..authorization import FilesystemIdentityResolver, PermissionDenied, ResolvedIdentity, UnresolvedIdentity
from ..authorization.discovery import effective_permissions
from ..browsing import NodeSummary
from ..errors import MissingNode, OwnershipNotFound, PolicyDecodingFailure
from ..models import AccessGrant, NodeId, NodeKind, Permission, Principal, PrincipalType
from ..transactions import FilesystemSession, FilesystemTransactions
from .models import (
    AvailableVisibility, CallerNodeSummary, CallerPermissions, RestrictedVisibility,
    UnavailableVisibility, Visibility,
)


def representable_principal(principal: Principal) -> bool:
    return (
        isinstance(principal, Principal)
        and principal.type in {PrincipalType.USER, PrincipalType.GROUP}
        and isinstance(principal.issuer, str) and bool(principal.issuer.strip())
        and isinstance(principal.id, str) and bool(principal.id.strip())
    )


def representable_grant(grant: AccessGrant, node_id: NodeId) -> bool:
    return (
        grant.node_id == node_id and representable_principal(grant.principal)
        and type(grant.recursive) is bool and isinstance(grant.permissions, set)
        and bool(grant.permissions) and all(isinstance(permission, Permission) for permission in grant.permissions)
    )


async def project_node_access(
    session: FilesystemSession, identity: ResolvedIdentity, node: NodeSummary,
) -> CallerNodeSummary:
    try:
        current = await session.namespace.get_node(node.id)
        ownership = await session.access_control.get_owner(node.id)
    except (MissingNode, OwnershipNotFound):
        raise PermissionDenied() from None
    policy_decodable = True
    try:
        grants = tuple(await session.access_control.list_grants(node.id))
    except PolicyDecodingFailure:
        if ownership.owner not in identity.principals:
            raise PermissionDenied() from None
        grants = ()
        policy_decodable = False
    permissions = effective_permissions(identity.principals, node.id, (ownership,), grants)
    if Permission.DISCOVER not in permissions:
        raise PermissionDenied()
    visibility: Visibility = RestrictedVisibility(type="restricted")
    if Permission.SHARE in permissions:
        if policy_decodable and representable_principal(ownership.owner) and all(
            representable_grant(grant, node.id) for grant in grants
        ):
            visibility = AvailableVisibility(
                type="available", scope="direct_node_policy", owner=ownership.owner,
                grants=grants, group_members_expanded=False,
            )
        else:
            visibility = UnavailableVisibility(type="unavailable")
    return CallerNodeSummary(
        **node.model_dump(exclude={"permissions", "visible_to", "sharing"}),
        permissions=CallerPermissions(
            can_discover=True, can_read=Permission.READ in permissions,
            can_write=Permission.WRITE in permissions,
            can_delete=current.kind == NodeKind.FILE and Permission.DELETE in permissions,
            can_share=Permission.SHARE in permissions,
        ),
        visible_to=visibility,
    )


class AccessMetadataService:
    def __init__(self, resolver: FilesystemIdentityResolver, transactions: FilesystemTransactions) -> None:
        self._resolver = resolver
        self._transactions = transactions

    async def enrich_nodes(
        self, caller: CallerSnapshot, nodes: Sequence[NodeSummary],
    ) -> list[CallerNodeSummary]:
        nodes = tuple(NodeSummary.model_validate(node) for node in nodes)
        identity = await self._resolver.resolve(caller)
        if isinstance(identity, UnresolvedIdentity):
            raise PermissionDenied()
        async with self._transactions.transaction() as session:
            return [await project_node_access(session, identity, node) for node in nodes]
