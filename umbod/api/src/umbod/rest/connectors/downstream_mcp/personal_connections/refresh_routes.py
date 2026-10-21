import json
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict

from umbod.core.connectors.downstream_mcp.personal_connections.inventory_models import PersonalConnectorUnavailable
from umbod.core.connectors.downstream_mcp.personal_connections.models import MissingCanonicalPrincipal
from umbod.core.connectors.downstream_mcp.personal_connections.refresh_models import PersonalRefreshChanged, PersonalRefreshConflict, PersonalRefreshReconnectRequired, PersonalRefreshUnsupported
from umbod.core.connectors.downstream_mcp.personal_connections.refresh_service import PersonalRefreshService

from .oauth_dependencies import require_personal_oauth
from .refresh_dependencies import get_personal_refresh_service


router = APIRouter(prefix="/connectors/mcp", dependencies=[Depends(require_personal_oauth)])


class PersonalRefreshResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Literal["refreshed"] = "refreshed"
    discovery_required: Literal[True] = True


def refresh_error(status: int, code: str) -> HTTPException:
    return HTTPException(status, detail={"code": code}, headers={"Cache-Control": "no-store"})


async def require_empty_refresh_body(request: Request) -> None:
    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > 1024:
            raise refresh_error(422, "personal_refresh_invalid_request")
        body.extend(chunk)
    try:
        value = json.loads(body)
        if not isinstance(value, dict) or value:
            raise ValueError()
    except (ValueError, UnicodeError):
        raise refresh_error(422, "personal_refresh_invalid_request") from None


@router.post("/{connector_id}/authorization/refresh", response_model=PersonalRefreshResponse)
async def refresh_personal_authorization(
    connector_id: str,
    body: Annotated[None, Depends(require_empty_refresh_body)],
    service: Annotated[PersonalRefreshService, Depends(get_personal_refresh_service)],
    response: Response,
) -> PersonalRefreshResponse:
    response.headers["Cache-Control"] = "no-store"
    try:
        await service.refresh(connector_id)
    except MissingCanonicalPrincipal:
        raise refresh_error(403, "personal_identity_unavailable") from None
    except PersonalConnectorUnavailable:
        raise refresh_error(404, "personal_connector_not_found") from None
    except PersonalRefreshUnsupported:
        raise refresh_error(409, "personal_refresh_unsupported") from None
    except PersonalRefreshConflict:
        raise refresh_error(409, "personal_refresh_conflict") from None
    except PersonalRefreshChanged:
        raise refresh_error(409, "personal_refresh_changed") from None
    except PersonalRefreshReconnectRequired:
        raise refresh_error(409, "personal_refresh_reconnect_required") from None
    except Exception:
        raise refresh_error(503, "personal_refresh_unavailable") from None
    return PersonalRefreshResponse()
