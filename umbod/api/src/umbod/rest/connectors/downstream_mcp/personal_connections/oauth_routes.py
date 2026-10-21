import json
from collections.abc import Awaitable
from typing import Annotated, TypeVar

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import ValidationError

from umbod.core.connectors.downstream_mcp.personal_connections.oauth_models import (
    PersonalOAuthConflict,
    PersonalOAuthProviderFailure,
    PersonalOAuthProviderUnsupported,
    PersonalOAuthUnavailable,
)
from umbod.core.connectors.downstream_mcp.personal_connections.oauth_service import PersonalOAuthService

from .oauth_dependencies import get_personal_oauth_service, require_personal_oauth
from .oauth_schemas import PersonalOAuthAttemptResponse, PersonalOAuthStartRequest, PersonalOAuthStartResponse


router = APIRouter(prefix="/connectors/mcp", dependencies=[Depends(require_personal_oauth)])
Service = Annotated[PersonalOAuthService, Depends(get_personal_oauth_service)]
Result = TypeVar("Result")


async def safe_oauth_operation(operation: Awaitable[Result]) -> Result:
    try:
        return await operation
    except PersonalOAuthUnavailable:
        raise HTTPException(404, detail={"code": "personal_oauth_unavailable"}) from None
    except PersonalOAuthConflict:
        raise HTTPException(409, detail={"code": "personal_oauth_conflict"}) from None
    except PersonalOAuthProviderUnsupported:
        raise HTTPException(422, detail={"code": "personal_oauth_provider_unsupported"}) from None
    except PersonalOAuthProviderFailure:
        raise HTTPException(502, detail={"code": "personal_oauth_provider_failure"}) from None


async def require_empty_oauth_body(request: Request) -> PersonalOAuthStartRequest:
    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > 1024:
            raise HTTPException(413, detail={"code": "personal_oauth_invalid_request"})
        body.extend(chunk)
    try:
        return PersonalOAuthStartRequest.model_validate(json.loads(body))
    except (ValueError, UnicodeError, ValidationError):
        raise HTTPException(422, detail={"code": "personal_oauth_invalid_request"}) from None


@router.post("/{connector_id}/oauth/attempts", status_code=201, response_model=PersonalOAuthStartResponse)
async def start_personal_oauth(
    connector_id: str,
    body: Annotated[PersonalOAuthStartRequest, Depends(require_empty_oauth_body)],
    service: Service, response: Response,
) -> PersonalOAuthStartResponse:
    result = await safe_oauth_operation(service.start(connector_id))
    response.headers["Cache-Control"] = "no-store"
    return PersonalOAuthStartResponse(
        **result.attempt.model_dump(), authorization_url=result.authorization_url.get_secret_value(),
    )


@router.get("/{connector_id}/oauth/attempts/{attempt_id}", response_model=PersonalOAuthAttemptResponse)
async def get_personal_oauth(
    connector_id: str, attempt_id: str, service: Service, response: Response,
) -> PersonalOAuthAttemptResponse:
    result = await safe_oauth_operation(service.get(connector_id, attempt_id))
    response.headers["Cache-Control"] = "no-store"
    return PersonalOAuthAttemptResponse(**result.model_dump())


@router.delete("/{connector_id}/oauth/attempts/{attempt_id}", response_model=PersonalOAuthAttemptResponse)
async def cancel_personal_oauth(
    connector_id: str, attempt_id: str, service: Service, response: Response,
) -> PersonalOAuthAttemptResponse:
    result = await safe_oauth_operation(service.cancel(connector_id, attempt_id))
    response.headers["Cache-Control"] = "no-store"
    return PersonalOAuthAttemptResponse(**result.model_dump())
