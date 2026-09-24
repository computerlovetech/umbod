from typing import Annotated

from fastmcp import FastMCP
from fastmcp.dependencies import CurrentFastMCP

from umbod.core.connectors.openapi.stores import OpenApiConnectorStore
from umbod.core.permissions.ports import GroupPermissionReader
from umbod.mcp.openapi_connectors.ports import (
    CurrentPrincipalGroups,
    GroupPermissionReaderFactory,
    OpenApiConnectorStoreFactory,
)
from umbod.mcp.openapi_connectors.principal import JwtCurrentPrincipalGroups


async def get_openapi_connector_store(server: Annotated[FastMCP, CurrentFastMCP()]) -> OpenApiConnectorStore:
    factory: OpenApiConnectorStoreFactory = server.openapi_connector_store_factory
    return await factory.create()


async def get_group_permission_reader(server: Annotated[FastMCP, CurrentFastMCP()]) -> GroupPermissionReader:
    factory: GroupPermissionReaderFactory = server.group_permission_reader_factory
    return await factory.create()


def get_current_principal_groups(server: Annotated[FastMCP, CurrentFastMCP()]) -> CurrentPrincipalGroups:
    return JwtCurrentPrincipalGroups(server.permission_group_claim)
