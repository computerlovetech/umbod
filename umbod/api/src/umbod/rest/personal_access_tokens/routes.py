from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response

from umbod.core.callers import CallerContext
from umbod.core.personal_access_tokens import (
    IssuePersonalAccessToken,
    PersonalAccessTokenAccess,
    PersonalAccessTokenGrant,
    PersonalAccessTokenMetadata,
    PersonalAccessTokenService,
    UnsupportedPersonalAccessTokenAccess,
    resolve_personal_access_token_access,
)
from umbod.rest.authentication.deps import get_caller_context

from .deps import get_personal_access_token_service
from .errors import token_operation
from .models import CreatedPersonalAccessToken, CreatePersonalAccessToken

router = APIRouter(prefix="/personal-access-tokens", tags=["personal-access-tokens"])

Caller = Annotated[CallerContext, Depends(get_caller_context)]
TokenService = Annotated[
    PersonalAccessTokenService, Depends(get_personal_access_token_service)
]


@router.post("", status_code=201, response_model=CreatedPersonalAccessToken)
async def create_personal_access_token(
    body: CreatePersonalAccessToken,
    response: Response,
    caller: Caller,
    service: TokenService,
) -> CreatedPersonalAccessToken:
    if body.expires_at <= datetime.now(timezone.utc):
        raise HTTPException(status_code=422, detail="Expiry must be in the future")
    access = PersonalAccessTokenAccess(
        grants=tuple(
            PersonalAccessTokenGrant(resource=resource, permission=permission)
            for resource, permission in body.permissions.items()
        )
    )
    try:
        resolved = resolve_personal_access_token_access(access)
    except UnsupportedPersonalAccessTokenAccess:
        raise HTTPException(
            status_code=422, detail="Unsupported personal access token access"
        ) from None
    async with token_operation():
        issued = await service.issue(
            caller,
            IssuePersonalAccessToken(
                name=body.name,
                expires_at=body.expires_at,
                audience=resolved.audience,
                scopes=resolved.scopes,
            ),
        )
    response.headers["Cache-Control"] = "no-store"
    return CreatedPersonalAccessToken(
        metadata=issued.metadata, token=issued.token.get_secret_value()
    )


@router.get("", response_model=tuple[PersonalAccessTokenMetadata, ...])
async def list_personal_access_tokens(
    response: Response,
    caller: Caller,
    service: TokenService,
) -> tuple[PersonalAccessTokenMetadata, ...]:
    async with token_operation():
        tokens = await service.list_tokens(caller)
    response.headers["Cache-Control"] = "no-store"
    return tokens


@router.delete("/{token_id}", status_code=204)
async def revoke_personal_access_token(
    token_id: str,
    caller: Caller,
    service: TokenService,
) -> Response:
    async with token_operation():
        revoked = await service.revoke(caller, token_id)
    if not revoked:
        raise HTTPException(status_code=404, detail="Personal access token not found")
    return Response(status_code=204, headers={"Cache-Control": "no-store"})
