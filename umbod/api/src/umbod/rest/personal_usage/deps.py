from collections.abc import Callable
from datetime import datetime, timezone
from typing import Annotated

from fastapi import Depends, HTTPException

from umbod.core.callers import CallerContext
from umbod.core.usage import UsageOwner, UsageReader, resolve_usage_owner
from umbod.core.usage.store import DatabaseUsageStore
from umbod.rest.authentication.authorization import JwtClaims
from umbod.rest.authentication.deps import get_caller_context, get_verified_access_claims
from umbod.rest.dependencies import get_connector_api_dependency_factories
from umbod.rest.factories import ConnectorApiDependencyFactories
from umbod.rest.user_catalogue.identity import catalogue_identity_key

from .models import PersonalUsageIdentity


def get_personal_usage_identity(
    caller: Annotated[CallerContext, Depends(get_caller_context)],
    claims: Annotated[JwtClaims, Depends(get_verified_access_claims)],
) -> PersonalUsageIdentity:
    owner = resolve_usage_owner(caller)
    if not isinstance(owner, UsageOwner):
        raise HTTPException(status_code=403, detail='Verified user identity is required')
    return PersonalUsageIdentity(owner_id=owner.owner_id, identity_key=catalogue_identity_key(claims.claims))


async def get_usage_reader(
    factories: Annotated[ConnectorApiDependencyFactories, Depends(get_connector_api_dependency_factories)],
) -> UsageReader:
    if not factories.settings.personal_usage.enabled:
        raise HTTPException(status_code=503, detail='Personal usage analytics are unavailable')
    try:
        await factories.persistence_runtime.readiness.ensure_ready()
    except Exception:
        raise HTTPException(status_code=503, detail='Personal usage analytics are unavailable') from None
    return DatabaseUsageStore(factories.persistence_runtime.database)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def get_usage_clock() -> Callable[[], datetime]:
    return utc_now
