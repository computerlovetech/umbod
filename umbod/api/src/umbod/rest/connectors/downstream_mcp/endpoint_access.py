from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends

from umbod.core.connectors.downstream_mcp.endpoint_access import (
    AnonymousMcpInitialization,
    CheckMcpEndpointAccess,
    McpEndpointAccessCheck,
    McpEndpointAccessResult,
)
from umbod.core.connectors.downstream_mcp.personal.oauth.metadata import (
    PersonalOAuthMetadataProvider,
)
from umbod.infrastructure import open_anonymous_mcp_initialization

from .personal_oauth_metadata import get_metadata_provider
from .preview_validation import BoundedPreviewRoute


class AccessCheckValidationRoute(BoundedPreviewRoute):
    @staticmethod
    def invalid_input_detail() -> dict[str, str]:
        return {"code": "invalid_mcp_endpoint_access_check"}


async def get_anonymous_mcp_initialization() -> AsyncIterator[
    AnonymousMcpInitialization
]:
    async with open_anonymous_mcp_initialization() as initialization:
        yield initialization


def get_endpoint_access_check(
    initialization: Annotated[
        AnonymousMcpInitialization, Depends(get_anonymous_mcp_initialization)
    ],
    oauth_metadata: Annotated[
        PersonalOAuthMetadataProvider, Depends(get_metadata_provider)
    ],
) -> McpEndpointAccessCheck:
    return McpEndpointAccessCheck(initialization, oauth_metadata)


router = APIRouter(route_class=AccessCheckValidationRoute)


@router.post("/check-access", response_model=McpEndpointAccessResult)
async def check_endpoint_access(
    command: CheckMcpEndpointAccess,
    access_check: Annotated[McpEndpointAccessCheck, Depends(get_endpoint_access_check)],
) -> McpEndpointAccessResult:
    return await access_check.check(command)
