from contextlib import AbstractAsyncContextManager
from typing import Protocol

from umbod.core.callers import CallerSnapshot
from umbod.core.groups.models import Group

from ..group_policy import GroupPolicy
from ..models import AccessGrant, NodeId
from ..ports import AccessControlDriver, NamespaceDriver
from .models import (
    EligibleSharingGroups, NodeGroupPolicyView, NodeSharingSummaries, ReplaceNodeGroupPolicy,
    ShareNodeGroupResult,
)


class RegisteredGroupReader(Protocol):
    async def registered_groups(self) -> tuple[Group, ...]: ...

    async def registered_group_ids(self) -> frozenset[str]: ...


class SharingGrantWriter(Protocol):
    async def upsert(self, grant: AccessGrant) -> None: ...


class SharingSession(Protocol):
    @property
    def namespace(self) -> NamespaceDriver: ...

    @property
    def access_control(self) -> AccessControlDriver: ...

    @property
    def groups(self) -> RegisteredGroupReader: ...

    @property
    def grants(self) -> SharingGrantWriter: ...


class SharingTransactions(Protocol):
    def transaction(self) -> AbstractAsyncContextManager[SharingSession]: ...


class FilesystemSharing(Protocol):
    async def share(
        self, snapshot: CallerSnapshot, node_id: NodeId, command: GroupPolicy,
    ) -> ShareNodeGroupResult: ...

    async def summarize_nodes(
        self, snapshot: CallerSnapshot, node_ids: tuple[NodeId, ...],
    ) -> NodeSharingSummaries: ...

    async def eligible_groups(self, snapshot: CallerSnapshot, node_id: NodeId) -> EligibleSharingGroups: ...

    async def inspect(self, snapshot: CallerSnapshot, node_id: NodeId) -> NodeGroupPolicyView: ...

    async def replace(
        self, snapshot: CallerSnapshot, node_id: NodeId, command: ReplaceNodeGroupPolicy,
    ) -> NodeGroupPolicyView: ...
