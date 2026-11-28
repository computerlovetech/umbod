from typing import Annotated

from fastapi import Depends
from pydantic import BaseModel, ConfigDict

from umbod.core.callers import AuthenticationProvenance, CallerContext, GroupMembership, LegacyGroupClaimPolicy
from umbod.core.connectors.downstream_mcp.adapters.identity import personal_identity_facts
from umbod.core.connectors.downstream_mcp.adapters.settings import personal_identity_policy_from_app_config
from umbod.core.connectors.downstream_mcp.personal.connections import (
    PersonalIdentityRejection,
    PersonalIdentityResolution,
    UnresolvedPersonalIdentity,
    canonical_principal,
)
from umbod.rest.authentication.authorization import JwtClaims
from umbod.rest.authentication.deps import get_caller_context, get_verified_access_claims
from umbod.rest.authentication.membership import RequestGroupMembershipResolver
from umbod.rest.dependencies import get_connector_api_dependency_factories
from umbod.rest.factories import ConnectorApiDependencyFactories

from .identity import catalogue_identity_key


class CatalogueCaller(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    caller: CallerContext
    groups: GroupMembership
    identity_key: str
    personal_identity: PersonalIdentityResolution


def get_catalogue_caller(
    factories: Annotated[ConnectorApiDependencyFactories, Depends(get_connector_api_dependency_factories)],
    claims: Annotated[JwtClaims, Depends(get_verified_access_claims)],
    caller: Annotated[CallerContext, Depends(get_caller_context)],
    group_membership_resolver: RequestGroupMembershipResolver,
) -> CatalogueCaller:
    resolution = canonical_principal(personal_identity_policy_from_app_config(factories.settings), personal_identity_facts(claims.claims))
    if caller.authentication == AuthenticationProvenance.UNAVAILABLE:
        resolution = UnresolvedPersonalIdentity(reason=PersonalIdentityRejection.AUTHENTICATION_DISABLED)
    return CatalogueCaller(
        caller=caller,
        groups=group_membership_resolver.resolve(
            claims.claims, (factories.settings.mcp.permission_group_claim,),
            LegacyGroupClaimPolicy.PERSONAL, caller.authentication,
        ),
        identity_key=catalogue_identity_key(claims.claims),
        personal_identity=resolution,
    )
