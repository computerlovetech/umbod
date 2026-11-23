from collections.abc import Awaitable, Callable
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from pydantic import Field, SecretStr

from umbod.core.harness_plugins import Harness
from umbod.core.persistence import Database
from umbod.core.personal_access_tokens.access import personal_access_token_policy
from umbod.core.personal_access_tokens.factory import SecurePersonalAccessTokenGenerator, UtcPersonalAccessTokenClock
from umbod.core.personal_access_tokens.install_claim_ports import InvalidInstallClaim
from umbod.core.personal_access_tokens.install_claim_store import DatabaseInstallClaimStore
from umbod.core.personal_access_tokens.install_claims import InstallClaimService
from umbod.core.personal_access_tokens.models import TokenModel, TokenOwner
from umbod.core.personal_access_tokens.service import PersonalAccessTokenIssuer
from umbod.rest.personal_access_tokens.deps import get_personal_access_token_database

from .deps import get_telemetry_owner, get_telemetry_setup_configuration
from .models import TelemetrySetup


class InstallClaimRoute(APIRoute):
    def get_route_handler(self) -> Callable[[Request], Awaitable[Response]]:
        handle = super().get_route_handler()

        async def handle_without_secret_errors(request: Request) -> Response:
            try:
                response = await handle(request)
            except RequestValidationError:
                response = JSONResponse({"detail": "Invalid install claim request"}, status_code=422)
            except HTTPException as error:
                response = JSONResponse({"detail": error.detail}, status_code=error.status_code)
            except InvalidInstallClaim:
                response = JSONResponse({"detail": "Invalid install claim"}, status_code=401)
            except Exception:
                response = JSONResponse({"detail": "Telemetry install claims unavailable"}, status_code=503)
            response.headers["Cache-Control"] = "no-store"
            return response

        return handle_without_secret_errors


personal_router = APIRouter(route_class=InstallClaimRoute, tags=["telemetry"])
public_router = APIRouter(route_class=InstallClaimRoute, tags=["install"])


class CreateInstallClaim(TokenModel):
    harness: Harness


class CreatedInstallClaim(TokenModel):
    code: str = Field(repr=False)


class RedeemedInstallClaim(TokenModel):
    token: str = Field(repr=False)
    logs_endpoint: str


def require_logs_endpoint(
    setup: Annotated[TelemetrySetup, Depends(get_telemetry_setup_configuration)],
) -> str:
    if setup.status != "available":
        raise HTTPException(status_code=503, detail="Telemetry is unavailable")
    return setup.logs_endpoint


def get_install_claim_service(
    database: Annotated[Database, Depends(get_personal_access_token_database)],
) -> InstallClaimService:
    return InstallClaimService(
        DatabaseInstallClaimStore(database),
        UtcPersonalAccessTokenClock(),
        PersonalAccessTokenIssuer(SecurePersonalAccessTokenGenerator(), personal_access_token_policy()),
    )


def bearer_claim(request: Request) -> SecretStr:
    headers = request.headers.getlist("authorization")
    if len(headers) != 1:
        raise InvalidInstallClaim()
    scheme, _, code = headers[0].partition(" ")
    if scheme.lower() != "bearer":
        raise InvalidInstallClaim()
    return SecretStr(code)


@personal_router.post("/telemetry/install-claims", status_code=201)
async def create_install_claim(
    body: CreateInstallClaim,
    owner: Annotated[TokenOwner, Depends(get_telemetry_owner)],
    logs_endpoint: Annotated[str, Depends(require_logs_endpoint)],
    service: Annotated[InstallClaimService, Depends(get_install_claim_service)],
) -> CreatedInstallClaim:
    code = await service.create(owner, body.harness, logs_endpoint)
    return CreatedInstallClaim(code=code.get_secret_value())


@public_router.post("/v1/{harness}/telemetry/redeem")
async def redeem_install_claim(
    harness: Harness,
    logs_endpoint: Annotated[str, Depends(require_logs_endpoint)],
    code: Annotated[SecretStr, Depends(bearer_claim)],
    service: Annotated[InstallClaimService, Depends(get_install_claim_service)],
) -> RedeemedInstallClaim:
    issued = await service.redeem(harness, code, logs_endpoint)
    return RedeemedInstallClaim(token=issued.token.get_secret_value(), logs_endpoint=logs_endpoint)
