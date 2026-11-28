from collections.abc import Mapping
from typing import Annotated

from fastmcp import FastMCP
from fastmcp.dependencies import CurrentFastMCP
from fastmcp.server.dependencies import get_access_token

from umbod.core.callers import GroupMembership, LegacyGroupClaimPolicy
from umbod.core.connectors.openapi.stores import OpenApiConnectorStore
from umbod.core.permissions.ports import GroupPermissionReader
from umbod.mcp.auth.caller import authentication_provenance
from umbod.mcp.auth.membership import server_group_membership_resolver
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
    return server_group_membership_resolver(server).resolve(
        claims, (server.permission_group_claim,), LegacyGroupClaimPolicy.OPENAPI,
        authentication_provenance(getattr(server, "auth", None)),
    )
