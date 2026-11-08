from typing import Protocol

from fastapi import FastAPI
from pydantic import SecretStr

from umbod.config import AppConfig
from umbod.config.identity_policy import local_development_identity_enabled
from umbod.core.callers import LOCAL_DEVELOPMENT_ISSUER
from umbod.core.personal_access_tokens import (
    InvalidPersonalAccessToken,
    ValidatePersonalAccessToken,
    create_personal_access_token_service,
)
from umbod.core.persistence import PersistenceRuntime
from umbod.core.personal_access_tokens.access import (
    TELEMETRY_INGEST_SCOPE,
    TELEMETRY_TOKEN_AUDIENCE,
    personal_access_token_policy,
)
from umbod.rest.telemetry.errors import TelemetryHttpError


class TelemetryPersonalAccessTokenVerifier(Protocol):
    async def verify(self, token: SecretStr) -> None: ...


class UnavailableTelemetryTokenVerifier:
    async def verify(self, token: SecretStr) -> None:
        raise TelemetryHttpError(401, "Invalid bearer credentials")


class DatabaseTelemetryTokenVerifier:
    def __init__(
        self, runtime: PersistenceRuntime, local_development_tokens_allowed: bool
    ) -> None:
        self._runtime = runtime
        self._local_development_tokens_allowed = local_development_tokens_allowed

    async def verify(self, token: SecretStr) -> None:
        try:
            await self._runtime.readiness.ensure_ready()
            service = create_personal_access_token_service(
                self._runtime.database,
                personal_access_token_policy(),
            )
            metadata = await service.validate(
                ValidatePersonalAccessToken(
                    token=token,
                    audience=TELEMETRY_TOKEN_AUDIENCE,
                    required_scopes=(TELEMETRY_INGEST_SCOPE,),
                )
            )
            if (
                metadata.owner.issuer == LOCAL_DEVELOPMENT_ISSUER
                and not self._local_development_tokens_allowed
            ):
                raise InvalidPersonalAccessToken()
        except InvalidPersonalAccessToken:
            raise TelemetryHttpError(401, "Invalid bearer credentials") from None
        except Exception:
            raise TelemetryHttpError(
                503, "Telemetry authentication is unavailable"
            ) from None


def get_telemetry_token_verifier() -> TelemetryPersonalAccessTokenVerifier:
    raise RuntimeError("Telemetry token verification is not installed")


def install_unavailable_telemetry_token_verifier(app: FastAPI) -> None:
    def provide_verifier() -> TelemetryPersonalAccessTokenVerifier:
        return UnavailableTelemetryTokenVerifier()

    app.dependency_overrides[get_telemetry_token_verifier] = provide_verifier


def install_telemetry_token_verifier(
    app: FastAPI,
    runtime: PersistenceRuntime,
    settings: AppConfig,
) -> None:
    local_development_tokens_allowed = local_development_identity_enabled(settings)

    def provide_verifier() -> TelemetryPersonalAccessTokenVerifier:
        return DatabaseTelemetryTokenVerifier(runtime, local_development_tokens_allowed)

    app.dependency_overrides[get_telemetry_token_verifier] = provide_verifier
