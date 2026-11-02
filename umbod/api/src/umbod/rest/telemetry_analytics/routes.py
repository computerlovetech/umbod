from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response

from umbod.core.telemetry.analytics import (
    AnalyticsResultLimitExceeded,
    LogCountResult,
    TelemetryAnalyticsReader,
    TelemetryAnalyticsUnavailable,
)
from umbod.rest.telemetry.dependencies import get_analytics_reader

from .models import LogCountRequest

router = APIRouter(prefix="/telemetry", tags=["telemetry-analytics"])


@router.post("/log-counts", response_model=LogCountResult)
async def count_logs(
    body: LogCountRequest,
    response: Response,
    reader: Annotated[TelemetryAnalyticsReader, Depends(get_analytics_reader)],
) -> LogCountResult:
    response.headers["Cache-Control"] = "no-store"
    try:
        return await reader.count_logs(body.to_query())
    except TelemetryAnalyticsUnavailable:
        raise HTTPException(
            status_code=503,
            detail="Telemetry analytics is unavailable. Enable the analytics backend and retry.",
            headers={"Cache-Control": "no-store"},
        ) from None
    except AnalyticsResultLimitExceeded:
        raise HTTPException(
            status_code=422,
            detail=(
                "Too many result groups. Narrow the time range, add filters, remove grouping "
                "dimensions, or increase the result limit (maximum 1000)."
            ),
            headers={"Cache-Control": "no-store"},
        ) from None
