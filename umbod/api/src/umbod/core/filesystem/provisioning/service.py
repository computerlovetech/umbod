from ..browsing import NodeSummary, summary
from ..errors import OwnershipNotFound, ProvisioningConflict
from ..models import SYSTEM_ROOT_OWNER, AccessGrant, NodeId, Ownership
from ..transactions import FilesystemSession, FilesystemTransactions
from .models import RootBootstrapSpec


async def bootstrap_completed(session: FilesystemSession, root_id: NodeId) -> bool:
    try:
        ownership = await session.access_control.get_owner(root_id)
    except OwnershipNotFound:
        if await session.namespace.list_children(root_id) or await session.access_control.list_grants(root_id):
            raise ProvisioningConflict("Unowned root contains children or grants") from None
        return False
    if ownership.owner != SYSTEM_ROOT_OWNER:
        raise ProvisioningConflict("Root already has a different owner")
    return True


class RootProvisioningService:
    def __init__(self, transactions: FilesystemTransactions) -> None:
        self._transactions = transactions

    async def provision(self, spec: RootBootstrapSpec) -> NodeSummary:
        async with self._transactions.transaction() as session:
            root = await session.namespace.get_root()
            if not await bootstrap_completed(session, root.id):
                await session.access_control.set_owner(Ownership(node_id=root.id, owner=SYSTEM_ROOT_OWNER))
                for grant in spec.grants:
                    await session.access_control.add_grant(AccessGrant(
                        node_id=root.id, principal=grant.principal,
                        permissions=set(grant.permissions), recursive=False,
                    ))
            result = summary(root)
        return result
