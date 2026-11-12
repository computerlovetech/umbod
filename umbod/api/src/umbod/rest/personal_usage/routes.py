from collections.abc import Callable
from datetime import datetime
from typing import Annotated, cast

from fastapi import APIRouter, Depends, HTTPException, Query, Response

from umbod.core.usage import OwnedUsageQuery, UsageReader, UsageWindowDays

from .deps import get_personal_usage_identity, get_usage_clock, get_usage_reader
from .models import PersonalUsageIdentity, PersonalUsageRequest, PersonalUsageResponse


router = APIRouter(tags=['personal-usage'])


@router.get('/usage', response_model=PersonalUsageResponse)
async def read_personal_usage(
    response: Response,
    query: Annotated[PersonalUsageRequest, Query()],
    identity: Annotated[PersonalUsageIdentity, Depends(get_personal_usage_identity)],
    reader: Annotated[UsageReader, Depends(get_usage_reader)],
    clock: Annotated[Callable[[], datetime], Depends(get_usage_clock)],
) -> PersonalUsageResponse:
    response.headers['Cache-Control'] = 'no-store'
    try:
        summary = await reader.count_usage(OwnedUsageQuery(
            owner_id=identity.owner_id, days=cast(UsageWindowDays, query.days), as_of=clock(),
        ))
    except Exception:
        raise HTTPException(status_code=503, detail='Personal usage analytics are unavailable') from None
    return PersonalUsageResponse(
        identity_key=identity.identity_key, range=summary.range,
        as_of=summary.as_of, totals=summary.totals, daily=summary.daily,
    )
