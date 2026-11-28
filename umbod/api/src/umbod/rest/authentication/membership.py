from enum import Enum, auto
from typing import Annotated

from fastapi import Depends

from umbod.core.callers import AuthenticationProvenance, CallerContext, CallerSnapshot
from umbod.rest.dependencies import get_connector_api_dependency_factories
from umbod.rest.factories import ConnectorApiDependencyFactories

from .authorization import JwtClaims
from .deps import get_caller_context, get_verified_access_claims


class VerifiedCallerSnapshotStatus(Enum):
    NOT_APPLICABLE = auto()


async def get_verified_caller_snapshot(
    caller: Annotated[CallerContext, Depends(get_caller_context)],
    claims: Annotated[JwtClaims, Depends(get_verified_access_claims)],
    factories: Annotated[ConnectorApiDependencyFactories, Depends(get_connector_api_dependency_factories)],
) -> CallerSnapshot | VerifiedCallerSnapshotStatus:
    if caller.authentication != AuthenticationProvenance.UPSTREAM_VERIFIED:
        return VerifiedCallerSnapshotStatus.NOT_APPLICABLE
    resolver = await factories.group_membership_source.capture()
    return CallerSnapshot(caller=caller, groups=resolver.resolve_verified(claims.claims))


RequestCallerSnapshot = Annotated[
    CallerSnapshot | VerifiedCallerSnapshotStatus, Depends(get_verified_caller_snapshot),
]
