from collections.abc import Mapping
from typing import Annotated

from fastmcp import FastMCP
from fastmcp.dependencies import CurrentFastMCP
from fastmcp.server.dependencies import get_access_token

from umbod.core.callers import GroupMembership
from umbod.mcp.auth.groups import capture_openapi_principal_groups
from umbod.core.connectors.openapi.stores import OpenApiConnectorStore
from umbod.core.permissions.ports import GroupPermissionReader
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
    token = get_access_token()
    if token is None:
        return GroupMembership(group_ids=())
    claims = getattr(token, 'claims', {})
    if not isinstance(claims, Mapping):
        return GroupMembership(group_ids=())
    return capture_openapi_principal_groups(claims, server.permission_group_claim)
