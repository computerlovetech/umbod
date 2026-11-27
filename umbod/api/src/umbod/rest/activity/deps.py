from collections.abc import Callable
from datetime import datetime, timezone
from typing import Annotated

from fastapi import Depends, HTTPException

from umbod.core.activity.models import (
    HarnessSummary,
    MissingSession,
    SessionDetailQuery,
    SessionListQuery,
    SessionReport,
    SessionSlice,
)
from umbod.core.activity.ports import ActivitySourceUnavailable, HarnessActivityReader, McpActivityReader
from umbod.core.activity.service import ActivityReadService
from umbod.core.callers import CallerContext
from umbod.core.persistence import PersistenceReadiness
from umbod.core.telemetry.analytics import OwnedLog, OwnersScope, TimeRange
from umbod.core.usage import OwnedUsageQuery, UsageOwner, UsageReader, UsageSummary, resolve_usage_owner
from umbod.core.usage.store import DatabaseUsageStore
from umbod.rest.authentication.authorization import JwtClaims
from umbod.rest.authentication.deps import get_caller_context, get_verified_access_claims
from umbod.rest.dependencies import get_connector_api_dependency_factories
from umbod.rest.factories import ConnectorApiDependencyFactories
from umbod.rest.telemetry_analytics.routes import get_personal_analytics_scope
from umbod.rest.user_catalogue.identity import catalogue_identity_key

from .models import ActivityIdentity


class DisabledHarnessActivityReader:
    async def summarize(self, owner: OwnedLog, window: TimeRange) -> HarnessSummary:
        raise ActivitySourceUnavailable()

    async def list_sessions(self, query: SessionListQuery) -> SessionSlice:
        raise ActivitySourceUnavailable()

    async def get_session(self, query: SessionDetailQuery) -> SessionReport | MissingSession:
        raise ActivitySourceUnavailable()


class PersonalMcpActivityReader:
    def __init__(self, enabled: bool, readiness: PersistenceReadiness, reader: UsageReader) -> None:
        self._enabled = enabled
        self._readiness = readiness
        self._reader = reader

    async def summarize(self, query: OwnedUsageQuery) -> UsageSummary:
        if not self._enabled:
            raise ActivitySourceUnavailable()
        try:
            await self._readiness.ensure_ready()
            return await self._reader.count_usage(query)
        except Exception:
            raise ActivitySourceUnavailable() from None


def get_harness_activity_reader() -> HarnessActivityReader:
    return DisabledHarnessActivityReader()


def get_harness_activity_owner(
    scope: Annotated[OwnersScope, Depends(get_personal_analytics_scope)],
) -> OwnedLog:
    return OwnedLog(kind="owned", owner_id=scope.owner_ids[0])


def get_activity_identity(
    caller: Annotated[CallerContext, Depends(get_caller_context)],
    claims: Annotated[JwtClaims, Depends(get_verified_access_claims)],
) -> ActivityIdentity:
    owner = resolve_usage_owner(caller)
    if not isinstance(owner, UsageOwner):
        raise HTTPException(status_code=403, detail="Verified user identity is required")
    return ActivityIdentity(owner=owner, identity_key=catalogue_identity_key(claims.claims))


def get_mcp_activity_usage_reader(
    factories: Annotated[ConnectorApiDependencyFactories, Depends(get_connector_api_dependency_factories)],
) -> UsageReader:
    return DatabaseUsageStore(factories.persistence_runtime.database)


def get_mcp_activity_reader(
    factories: Annotated[ConnectorApiDependencyFactories, Depends(get_connector_api_dependency_factories)],
    reader: Annotated[UsageReader, Depends(get_mcp_activity_usage_reader)],
) -> McpActivityReader:
    return PersonalMcpActivityReader(factories.settings.personal_usage.enabled, factories.persistence_runtime.readiness, reader)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def get_activity_clock() -> Callable[[], datetime]:
    return _utc_now


def get_activity_read_service(
    harness: Annotated[HarnessActivityReader, Depends(get_harness_activity_reader)],
    mcp: Annotated[McpActivityReader, Depends(get_mcp_activity_reader)],
    clock: Annotated[Callable[[], datetime], Depends(get_activity_clock)],
) -> ActivityReadService:
    return ActivityReadService(harness, mcp, clock)
