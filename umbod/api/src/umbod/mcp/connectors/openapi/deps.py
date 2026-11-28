from dataclasses import dataclass
from typing import Annotated

from fastmcp import FastMCP
from fastmcp.dependencies import CurrentFastMCP
from fastmcp.server.dependencies import get_access_token

from umbod.core.callers import GroupMembership, LegacyGroupClaimPolicy
from umbod.core.connectors.openapi.stores import OpenApiConnectorStore
from umbod.core.permissions.domain import GroupPermissionSet
from umbod.core.permissions.ports import GroupPermissionLookup, GroupPermissionReader
from umbod.mcp.auth.membership import McpAccessTokenAvailability, capture_mcp_caller, restricted_mcp_grants
from umbod.mcp.connectors.openapi.ports import (
    GroupPermissionReaderFactory,
    OpenApiConnectorStoreFactory,
)


@dataclass(frozen=True)
class OpenApiPermissionScope:
    groups: tuple[str, ...]
    reader: GroupPermissionLookup


@dataclass(frozen=True)
class _InstanceGrantLookup:
    grants: GroupPermissionSet

    async def list_group_permissions(self, group_id: str) -> GroupPermissionSet:
        if group_id == self.grants.group_id:
            return self.grants
        return GroupPermissionSet(group_id=group_id, connector_ids=(), capabilities=())


async def capture_openapi_permissions(server: FastMCP) -> OpenApiPermissionScope:
    grants = restricted_mcp_grants(server, get_access_token() or McpAccessTokenAvailability.UNAVAILABLE)
    if grants is not None:
        groups = (grants.group_id,) if grants.group_id else ()
        return OpenApiPermissionScope(groups, _InstanceGrantLookup(grants))
    return OpenApiPermissionScope(
        capture_openapi_groups(server).group_ids, await get_group_permission_reader(server),
    )


async def get_openapi_connector_store(server: Annotated[FastMCP, CurrentFastMCP()]) -> OpenApiConnectorStore:
    factory: OpenApiConnectorStoreFactory = server.openapi_connector_store_factory
    return await factory.create()


async def get_group_permission_reader(server: Annotated[FastMCP, CurrentFastMCP()]) -> GroupPermissionReader:
    factory: GroupPermissionReaderFactory = server.group_permission_reader_factory
    return await factory.create()


def capture_openapi_groups(server: FastMCP) -> GroupMembership:
    return capture_mcp_caller(
        server, get_access_token() or McpAccessTokenAvailability.UNAVAILABLE, (server.permission_group_claim,), LegacyGroupClaimPolicy.OPENAPI,
    ).groups
