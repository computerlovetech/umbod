from typing import Annotated

from fastmcp import FastMCP
from fastmcp.dependencies import CurrentFastMCP
from fastmcp.server.dependencies import get_access_token

from umbod.core.callers import GroupMembership, LegacyGroupClaimPolicy
from umbod.core.connectors.openapi.stores import OpenApiConnectorStore
from umbod.core.permissions.ports import GroupPermissionReader
from umbod.mcp.auth.membership import McpAccessTokenAvailability, capture_mcp_caller
from umbod.mcp.connectors.openapi.ports import (
    GroupPermissionReaderFactory,
    OpenApiConnectorStoreFactory,
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
