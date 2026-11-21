from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from umbod.core.mcp_registry import (
    McpRegistry,
    RegistryPage,
    RegistrySearch,
    RegistryUnavailableError,
)
from umbod.infrastructure import open_official_mcp_registry

router = APIRouter(prefix="/registry")


async def get_mcp_registry() -> AsyncIterator[McpRegistry]:
    async with open_official_mcp_registry() as registry:
        yield registry


@router.get("/search", response_model=RegistryPage)
async def search_mcp_registry(
    query: Annotated[RegistrySearch, Query()],
    registry: Annotated[McpRegistry, Depends(get_mcp_registry)],
) -> RegistryPage:
    try:
        return await registry.search(query)
    except RegistryUnavailableError:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"code": "mcp_registry_unavailable"},
        ) from None
