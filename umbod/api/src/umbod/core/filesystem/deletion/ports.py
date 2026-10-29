from typing import Protocol

from umbod.core.callers import CallerSnapshot

from ..models import NodeId


class FilesystemDeletion(Protocol):
    async def check_delete_eligibility(self, snapshot: CallerSnapshot, node_id: NodeId) -> None: ...

    async def delete_file(
        self, snapshot: CallerSnapshot, node_id: NodeId, *, expected_revision: int,
    ) -> None: ...
