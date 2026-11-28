from typing import Annotated

from fastapi import Depends, HTTPException

from umbod.config import AppConfig
from umbod.core.administrator import AdministratorAccess
from umbod.core.administrator.connector_configuration import AdministratorPrincipal
from umbod.core.agent_tokens import AgentCredentialService, create_agent_credential_service
from umbod.rest.authentication.authorization import JwtClaims
from umbod.rest.authentication.deps import get_verified_access_claims
from umbod.rest.dependencies import get_connector_api_dependency_factories
from umbod.rest.factories import ConnectorApiDependencyFactories
from umbod.rest.instance_configuration.dependencies import get_app_config


def get_agent_token_administrator(
    config: Annotated[AppConfig, Depends(get_app_config)],
    verified_claims: Annotated[JwtClaims, Depends(get_verified_access_claims)],
) -> AdministratorPrincipal:
    claim = verified_claims.claims.get(config.admin_authentication.membership_claim)
    if not isinstance(claim, list):
        raise HTTPException(status_code=403, detail="Forbidden")
    return AdministratorPrincipal(
        memberships=tuple(value for value in claim if isinstance(value, str))
    )


async def get_agent_token_service(
    config: Annotated[AppConfig, Depends(get_app_config)],
    factories: Annotated[
        ConnectorApiDependencyFactories, Depends(get_connector_api_dependency_factories)
    ],
) -> AgentCredentialService:
    runtime = factories.persistence_runtime
    try:
        await runtime.readiness.ensure_ready()
    except Exception:
        raise HTTPException(status_code=503) from None
    return create_agent_credential_service(
        runtime.database,
        AdministratorAccess(config.admin_authentication.required_membership),
    )
