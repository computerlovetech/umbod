from typing import Annotated, cast

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Response
from pydantic import AfterValidator, ConfigDict, Field

from umbod.proxies import Model
from umbod.core.activity.cursor import InvalidSessionCursor
from umbod.core.activity.models import (
    CursorToken,
    FirstPage,
    HarnessSource,
    MissingSession,
    SearchTerm,
    SessionKey,
    SessionLimit,
    SourceUnavailable,
)
from umbod.core.activity.ports import ActivitySourceUnavailable
from umbod.core.activity.service import ActivityReadService
from umbod.core.telemetry.analytics import OwnedLog
from umbod.core.usage import UsageWindowDays

from .deps import get_activity_identity, get_activity_read_service, get_harness_activity_owner
from .models import (
    ActivityIdentity, ActivityOverviewResponse, ActivitySessionResponse, ActivitySessionsResponse, ActivityWindowQuery,
)


class ActivitySessionsQuery(ActivityWindowQuery):
    q: SearchTerm = ""
    cursor: Annotated[str, Field(min_length=1, max_length=16384)] | None = None
    limit: SessionLimit = 20

    def page_cursor(self) -> FirstPage | CursorToken:
        if self.cursor is None:
            return FirstPage(kind="first")
        return CursorToken(value=self.cursor)


class ActivitySessionDetailQuery(Model):
    model_config = ConfigDict(extra="forbid")


def valid_session_id(value: str) -> str:
    if not value.strip() or value in (".", "..") or "\x00" in value:
        raise ValueError("Invalid session ID")
    return value


router = APIRouter(prefix="/activity", tags=["activity"])
ActivityService = Annotated[ActivityReadService, Depends(get_activity_read_service)]
HarnessOwner = Annotated[OwnedLog, Depends(get_harness_activity_owner)]
VerifiedActivityIdentity = Annotated[ActivityIdentity, Depends(get_activity_identity)]


@router.get(
    "",
    operation_id="activity__overview",
    response_model=ActivityOverviewResponse,
    responses={503: {"model": ActivityOverviewResponse}},
)
async def read_activity_overview(
    response: Response,
    query: Annotated[ActivityWindowQuery, Query()],
    harness_owner: HarnessOwner,
    identity: VerifiedActivityIdentity,
    service: ActivityService,
) -> ActivityOverviewResponse:
    overview = await service.get_overview(harness_owner, identity.owner, cast(UsageWindowDays, query.days))
    if isinstance(overview.harness, SourceUnavailable) and isinstance(overview.mcp, SourceUnavailable):
        response.status_code = 503
    return ActivityOverviewResponse(
        identity_key=identity.identity_key, period=overview.period, harness=overview.harness, mcp=overview.mcp,
    )


@router.get("/sessions", operation_id="activity__sessions", response_model=ActivitySessionsResponse)
async def list_activity_sessions(
    query: Annotated[ActivitySessionsQuery, Query()],
    owner: HarnessOwner,
    identity: VerifiedActivityIdentity,
    service: ActivityService,
) -> ActivitySessionsResponse:
    try:
        sessions = await service.list_sessions(owner, cast(UsageWindowDays, query.days), query.q, query.page_cursor(), query.limit)
    except InvalidSessionCursor:
        raise HTTPException(status_code=422, detail="Invalid session cursor") from None
    except ActivitySourceUnavailable:
        raise HTTPException(status_code=503, detail="Harness activity is unavailable") from None
    return ActivitySessionsResponse(
        identity_key=identity.identity_key, period=sessions.period, sessions=sessions.sessions, page=sessions.page,
    )


@router.get("/sessions/{source}/{session_id:path}", operation_id="activity__session", response_model=ActivitySessionResponse)
async def read_activity_session(
    source: HarnessSource,
    session_id: Annotated[str, Path(min_length=1, max_length=1024), AfterValidator(valid_session_id)],
    query: Annotated[ActivitySessionDetailQuery, Query()],
    owner: HarnessOwner,
    identity: VerifiedActivityIdentity,
    service: ActivityService,
) -> ActivitySessionResponse:
    try:
        session = await service.get_session(owner, SessionKey(source=source, session_id=session_id))
    except ActivitySourceUnavailable:
        raise HTTPException(status_code=503, detail="Harness activity is unavailable") from None
    if isinstance(session, MissingSession):
        raise HTTPException(status_code=404, detail="Session not found")
    return ActivitySessionResponse(
        identity_key=identity.identity_key,
        session=session.session,
        top_tools=session.top_tools,
        failed_tools=session.failed_tools,
        has_more_failed_tools=session.has_more_failed_tools,
        skill_activations=session.skill_activations,
    )
