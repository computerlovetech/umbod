from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response

from umbod.core.callers import LOCAL_DEVELOPMENT_ISSUER, AuthenticationProvenance, CallerContext
from umbod.core.personal_access_tokens import UntrustedPersonalAccessTokenCaller
from umbod.core.personal_access_tokens.ports import PersonalAccessTokenOwnerResolver
from umbod.core.telemetry.analytics import (
    InstanceScope,
    LogCountQuery,
    LogCountResult,
    OwnersScope,
    TelemetryAnalyticsReader,
    TelemetryAnalyticsUnavailable,
    analytics_owner_id,
)
from umbod.rest.authentication.deps import get_caller_context
from umbod.rest.personal_access_tokens.deps import get_personal_access_token_owner_resolver
from umbod.rest.telemetry.dependencies import get_analytics_reader

from .models import LogCountRequest

router = APIRouter(prefix="/telemetry", tags=["telemetry-analytics"])
personal_router = APIRouter(prefix="/telemetry", tags=["telemetry-analytics"])


def get_personal_analytics_scope(
    caller: Annotated[CallerContext, Depends(get_caller_context)],
    owner_resolver: Annotated[
        PersonalAccessTokenOwnerResolver, Depends(get_personal_access_token_owner_resolver)
    ],
) -> OwnersScope:
    try:
        owner = owner_resolver.resolve(caller)
    except UntrustedPersonalAccessTokenCaller:
        raise HTTPException(status_code=403, detail="Verified identity required") from None
    if owner.issuer == LOCAL_DEVELOPMENT_ISSUER and caller.authentication != AuthenticationProvenance.LOCAL_SIMULATION:
        raise HTTPException(status_code=403, detail="Verified identity required")
    return OwnersScope(kind="owners", owner_ids=(analytics_owner_id(owner.issuer, owner.subject),))


@router.post("/log-counts", response_model=LogCountResult)
async def count_logs(
    body: LogCountRequest,
    response: Response,
    reader: Annotated[TelemetryAnalyticsReader, Depends(get_analytics_reader)],
) -> LogCountResult:
    return await _read_count(body.to_query(InstanceScope(kind="instance")), response, reader)


@personal_router.post("/log-counts", response_model=LogCountResult)
async def count_personal_logs(
    body: LogCountRequest,
    response: Response,
    scope: Annotated[OwnersScope, Depends(get_personal_analytics_scope)],
    reader: Annotated[TelemetryAnalyticsReader, Depends(get_analytics_reader)],
) -> LogCountResult:
    return await _read_count(body.to_query(scope), response, reader)


async def _read_count(
    query: LogCountQuery, response: Response, reader: TelemetryAnalyticsReader,
) -> LogCountResult:
    response.headers["Cache-Control"] = "no-store"
    try:
        return await reader.count_logs(query)
    except TelemetryAnalyticsUnavailable:
        raise HTTPException(
            status_code=503,
            detail="Telemetry analytics is unavailable. Enable the analytics backend and retry.",
            headers={"Cache-Control": "no-store"},
        ) from None
