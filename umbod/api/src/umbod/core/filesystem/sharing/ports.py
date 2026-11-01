from contextlib import AbstractAsyncContextManager
from typing import Protocol

from umbod.core.callers import CallerSnapshot
from umbod.core.groups.models import Group
from umbod.core.identity_directory.ports import ObservedUserDirectory

from ..models import AccessGrant, NodeId
from ..ports import AccessControlDriver, NamespaceDriver
from .models import (
    EligibleSharingGroups, NodePolicyView, NodeSharingSummaries, ReplaceNodePolicy,
    ShareNodePolicy, ShareNodeResult, SharingScope, SharingRecipientSearchQuery, SharingRecipientSearchResult,
)


class RegisteredGroupReader(Protocol):
    async def registered_groups(self) -> tuple[Group, ...]: ...

    async def registered_group_ids(self) -> frozenset[str]: ...


class SharingGrantWriter(Protocol):
    async def upsert(self, grant: AccessGrant) -> None: ...


class SharingSession(Protocol):
    @property
    def users(self) -> ObservedUserDirectory: ...

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
    async def search_recipients(
        self, snapshot: CallerSnapshot, node_id: NodeId, query: SharingRecipientSearchQuery,
    ) -> SharingRecipientSearchResult: ...

    async def share(
        self, snapshot: CallerSnapshot, node_id: NodeId, command: ShareNodePolicy,
    ) -> ShareNodeResult: ...

    async def summarize_nodes(
        self, snapshot: CallerSnapshot, node_ids: tuple[NodeId, ...],
    ) -> NodeSharingSummaries: ...

    async def eligible_groups(self, snapshot: CallerSnapshot, node_id: NodeId) -> EligibleSharingGroups: ...

    async def inspect(
        self, snapshot: CallerSnapshot, node_id: NodeId, scope: SharingScope,
    ) -> NodePolicyView: ...

    async def replace(
        self, snapshot: CallerSnapshot, node_id: NodeId, command: ReplaceNodePolicy,
    ) -> NodePolicyView: ...
