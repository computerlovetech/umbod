from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from starlette.exceptions import HTTPException

from umbod.core.administrator import AdministratorAccessDenied
from umbod.core.agent_tokens import (
    AgentCredentialConflict,
    AgentGroupNotFound,
    AgentNotFound,
    InvalidAgentCredentialExpiry,
)
from umbod.rest.authentication.deps import ADMIN_AUTHORIZED_STATE_KEY


def _error_response(status_code: int, detail: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"detail": detail},
        headers={"Cache-Control": "no-store"},
    )


class AgentTokenRoute(APIRoute):
    def get_route_handler(self) -> Callable[[Request], Awaitable[Response]]:
        handler = super().get_route_handler()

        async def handle(request: Request) -> Response:
            if getattr(request.state, ADMIN_AUTHORIZED_STATE_KEY, False) is not True:
                return _error_response(401, "Unauthorized")
            try:
                response = await handler(request)
            except RequestValidationError:
                return _error_response(422, "Invalid agent token request")
            except InvalidAgentCredentialExpiry:
                return _error_response(422, "Expiry must be in the future")
            except AgentGroupNotFound:
                return _error_response(404, "Agent group not found")
            except AgentNotFound:
                return _error_response(404, "Agent not found")
            except AgentCredentialConflict:
                return _error_response(409, "Agent credential conflict")
            except AdministratorAccessDenied:
                return _error_response(403, "Forbidden")
            except HTTPException as error:
                if error.status_code == 401:
                    return _error_response(401, "Unauthorized")
                if error.status_code == 403:
                    return _error_response(403, "Forbidden")
                if error.status_code in (400, 422):
                    return _error_response(422, "Invalid agent token request")
                if error.status_code == 503:
                    return _error_response(503, "Agent token storage unavailable")
                return _error_response(500, "Agent token request failed")
            except Exception:
                return _error_response(500, "Agent token request failed")
            response.headers["Cache-Control"] = "no-store"
            return response

        return handle
