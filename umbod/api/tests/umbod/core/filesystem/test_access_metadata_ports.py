from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any
from unittest.mock import AsyncMock, Mock

import pytest

from umbod.core.filesystem.access import AccessMetadataService
from umbod.core.filesystem.authorization import VerifiedIdentityResolver
from umbod.core.filesystem.browsing import summary
from umbod.core.filesystem.models import (
    AccessGrant, NodeKind, NodeMetadata, Ownership, Permission, Principal, PrincipalType,
)
from umbod.core.filesystem.namespace import ROOT_ID, initial_root, new_node
from tests.umbod.core.filesystem.test_effective_permissions import policy
from umbod.core.filesystem.ports import AccessControlDriver, NamespaceDriver
from umbod.core.filesystem.transactions import FilesystemSession
from tests.umbod.core.filesystem.test_verified_identity import snapshot


class InMemoryMetadataTransactions:
    def __init__(self, session: FilesystemSession) -> None:
        self._session = session

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[FilesystemSession]:
        yield self._session


@pytest.mark.asyncio
@pytest.mark.parametrize("updates", [
    {"recursive": 0}, {"recursive": ""},
    {"permissions": {"invented"}}, {"permissions": set()},
    {"principal": Principal(type=PrincipalType.SYSTEM, issuer="protected", id="rule")},
    {"principal": Principal(type=PrincipalType.USER, issuer="", id="malformed")},
])
async def test_direct_policy_representability_is_irrelevant_to_namespace_authority(updates: dict[str, Any]) -> None:
    node = new_node(ROOT_ID, "node", NodeKind.FILE, NodeMetadata(content_type={}, attributes={}))
    owner = Principal(type=PrincipalType.USER, issuer="issuer", id="alice")
    namespace = Mock(spec=NamespaceDriver)
    namespace.get_node = AsyncMock(side_effect=lambda node_id: initial_root() if node_id == ROOT_ID else node)
    policies = Mock(spec=AccessControlDriver)
    namespace_root = new_node(ROOT_ID, "namespace", NodeKind.DIRECTORY, node.metadata)
    node = node.model_copy(update={"parent_id": namespace_root.id})
    namespace.get_node = AsyncMock(side_effect=lambda node_id: initial_root() if node_id == ROOT_ID else namespace_root if node_id == namespace_root.id else node)
    policies.list_namespace_policies = AsyncMock(return_value=[policy(namespace_root.id)])
    policies.get_owner = AsyncMock(return_value=Ownership(node_id=node.id, owner=owner))
    grant = AccessGrant(
        node_id=node.id, principal=Principal(type=PrincipalType.USER, issuer="foreign", id="unknown"),
        permissions={Permission.READ}, recursive=False,
    ).model_copy(update=updates)
    policies.list_grants = AsyncMock(return_value=[grant])
    service = AccessMetadataService(
        VerifiedIdentityResolver(), InMemoryMetadataTransactions(FilesystemSession(namespace, policies)),
    )
    result = (await service.enrich_nodes(snapshot("alice", "issuer", ()), [summary(node)]))[0]
    assert result.visible_to.type == "namespace"
    policies.get_owner.assert_not_awaited()
    policies.list_grants.assert_not_awaited()
    assert result.permissions.can_delete is True
    policies.add_grant.assert_not_called()
    policies.set_owner.assert_not_called()
