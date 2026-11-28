from typing import Annotated

from fastapi import APIRouter, Depends, Response

from umbod.core.administrator.connector_configuration import AdministratorPrincipal
from umbod.core.agent_tokens import (
    AgentCredentialService,
    AgentNotFound,
    CreateAgent,
    RotateAgentCredential,
)
from umbod.core.agent_tokens.models import UuidHex

from .dependencies import get_agent_token_administrator, get_agent_token_service
from .models import (
    AgentTokenMetadataResponse,
    IssuedAgentTokenResponse,
    RotateAgentTokenRequest,
)
from .route_policy import AgentTokenRoute


router = APIRouter(
    prefix="/tokens/agents", tags=["agent-tokens"], route_class=AgentTokenRoute
)
AgentTokenServiceDependency = Annotated[
    AgentCredentialService, Depends(get_agent_token_service)
]
AgentTokenAdministratorDependency = Annotated[
    AdministratorPrincipal, Depends(get_agent_token_administrator)
]


@router.post("", status_code=201)
async def create_agent(
    request: CreateAgent,
    administrator: AgentTokenAdministratorDependency,
    service: AgentTokenServiceDependency,
) -> IssuedAgentTokenResponse:
    issued = await service.create(administrator, request)
    return IssuedAgentTokenResponse.from_issued(issued)


@router.get("")
async def list_agents(
    administrator: AgentTokenAdministratorDependency,
    service: AgentTokenServiceDependency,
) -> tuple[AgentTokenMetadataResponse, ...]:
    agents = await service.list_agents(administrator)
    return tuple(AgentTokenMetadataResponse.model_validate(agent) for agent in agents)


@router.post("/{agent_id}/rotate")
async def rotate_agent(
    agent_id: UuidHex,
    request: RotateAgentTokenRequest,
    administrator: AgentTokenAdministratorDependency,
    service: AgentTokenServiceDependency,
) -> IssuedAgentTokenResponse:
    issued = await service.rotate(
        administrator,
        RotateAgentCredential(agent_id=agent_id, expires_at=request.expires_at),
    )
    return IssuedAgentTokenResponse.from_issued(issued)


@router.delete("/{agent_id}", status_code=204)
async def revoke_agent(
    agent_id: UuidHex,
    administrator: AgentTokenAdministratorDependency,
    service: AgentTokenServiceDependency,
) -> Response:
    if not await service.revoke(administrator, agent_id):
        raise AgentNotFound("Agent credential not found")
    return Response(status_code=204)
