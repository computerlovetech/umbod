from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import httpx
import pytest
import pytest_asyncio

from tests.persistence_runtime import prepared_inmemory_runtime
from umbod.config import AppConfig, OtlpReceiverConfig
from umbod.core.callers import (
    AuthenticationProvenance,
    CallerContext,
    DeclaredIssuer,
    SubjectIdentity,
)
from umbod.core.personal_access_tokens import (
    IssuePersonalAccessToken,
    IssuedPersonalAccessToken,
    PersonalAccessTokenPolicy,
    PersonalAccessTokenService,
)
from umbod.core.personal_access_tokens.factory import SecurePersonalAccessTokenGenerator
from umbod.core.personal_access_tokens.store import DatabasePersonalAccessTokenStore
from umbod.core.persistence import Database, PersistenceReadiness, PersistenceRuntime
from umbod.core.telemetry import TelemetryExport, TelemetrySink
from umbod.core.personal_access_tokens.access import (
    TELEMETRY_INGEST_SCOPE,
    TELEMETRY_TOKEN_AUDIENCE,
)
from umbod.rest.telemetry import install_telemetry_receiver
from umbod.rest.telemetry.dependencies import get_receiver_config, get_telemetry_sink
from umbod.rest.telemetry.token_authentication import install_telemetry_token_verifier
from fastapi import FastAPI


class AcceptedSink:
    def export(self, batch: TelemetryExport) -> None:
        pass


class UnavailableTokenRuntime:
    def __init__(self, database: Database) -> None:
        self._database = database

    @property
    def database(self) -> Database:
        return self._database

    @property
    def readiness(self) -> PersistenceReadiness:
        return self

    async def ensure_ready(self) -> None:
        raise RuntimeError("private-database-information")

    async def shutdown(self) -> None:
        pass


class EarlierClock:
    def now(self) -> datetime:
        return datetime.now(timezone.utc) - timedelta(days=1)


@dataclass(frozen=True)
class TokenReceiver:
    app: FastAPI
    runtime: PersistenceRuntime
    service: PersonalAccessTokenService
    caller: CallerContext


@pytest_asyncio.fixture
async def receiver() -> AsyncIterator[TokenReceiver]:
    runtime = await prepared_inmemory_runtime()
    try:
        app = FastAPI()
        install_telemetry_receiver(
            app,
            AppConfig(
                otlp_receiver=OtlpReceiverConfig(
                    enabled=True, bearer_token="legacy-token"
                ),
            ),
        )
        install_telemetry_token_verifier(app, runtime, AppConfig())

        def provide_sink() -> TelemetrySink:
            return AcceptedSink()

        app.dependency_overrides[get_telemetry_sink] = provide_sink
        service = PersonalAccessTokenService(
            store=DatabasePersonalAccessTokenStore(runtime.database),
            clock=EarlierClock(),
            generator=SecurePersonalAccessTokenGenerator(),
            policy=PersonalAccessTokenPolicy(
                allowed_scopes=(TELEMETRY_INGEST_SCOPE, "telemetry:read"),
            ),
        )
        caller = CallerContext(
            authentication=AuthenticationProvenance.UPSTREAM_VERIFIED,
            subject=SubjectIdentity(
                issuer=DeclaredIssuer(value="https://issuer.example.test"),
                subject="alice",
            ),
        )
        yield TokenReceiver(app=app, runtime=runtime, service=service, caller=caller)
    finally:
        await runtime.shutdown()


async def issue(
    receiver: TokenReceiver,
    audience: str,
    scopes: tuple[str, ...],
    expires_at: datetime,
) -> IssuedPersonalAccessToken:
    return await receiver.service.issue(
        receiver.caller,
        IssuePersonalAccessToken(
            name="Codex",
            audience=audience,
            scopes=scopes,
            expires_at=expires_at,
        ),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("signal", ["logs", "traces", "metrics"])
@pytest.mark.parametrize("content_type", ["application/json", "application/x-protobuf"])
async def test_telemetry_audience_and_ingestion_scope_allow_each_signal(
    receiver: TokenReceiver,
    signal: str,
    content_type: str,
) -> None:
    issued = await issue(
        receiver,
        TELEMETRY_TOKEN_AUDIENCE,
        (TELEMETRY_INGEST_SCOPE,),
        datetime.now(timezone.utc) + timedelta(hours=1),
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=receiver.app),
        base_url="http://collector",
    ) as client:
        response = await client.post(
            f"/v1/{signal}",
            content=b"{}" if content_type == "application/json" else b"",
            headers={
                "Authorization": f"Bearer {issued.token.get_secret_value()}",
                "Content-Type": content_type,
            },
        )
    assert response.status_code == 200


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "audience,scopes",
    [
        ("umbod:api", (TELEMETRY_INGEST_SCOPE,)),
        (TELEMETRY_TOKEN_AUDIENCE, ("telemetry:read",)),
    ],
)
async def test_other_purposes_are_denied_before_payload_parsing(
    receiver: TokenReceiver,
    audience: str,
    scopes: tuple[str, ...],
) -> None:
    issued = await issue(
        receiver,
        audience,
        scopes,
        datetime.now(timezone.utc) + timedelta(hours=1),
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=receiver.app),
        base_url="http://collector",
    ) as client:
        response = await client.post(
            "/v1/logs",
            content="malformed",
            headers={"Authorization": f"Bearer {issued.token.get_secret_value()}"},
        )
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert issued.token.get_secret_value() not in response.text


@pytest.mark.asyncio
async def test_expired_token_is_denied(receiver: TokenReceiver) -> None:
    issued = await issue(
        receiver,
        TELEMETRY_TOKEN_AUDIENCE,
        (TELEMETRY_INGEST_SCOPE,),
        datetime.now(timezone.utc) - timedelta(minutes=1),
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=receiver.app),
        base_url="http://collector",
    ) as client:
        response = await client.post(
            "/v1/logs",
            json={},
            headers={"Authorization": f"Bearer {issued.token.get_secret_value()}"},
        )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_revocation_is_immediate_and_never_falls_back_to_shared_bearer(
    receiver: TokenReceiver,
) -> None:
    issued = await issue(
        receiver,
        TELEMETRY_TOKEN_AUDIENCE,
        (TELEMETRY_INGEST_SCOPE,),
        datetime.now(timezone.utc) + timedelta(hours=1),
    )

    def provide_config() -> OtlpReceiverConfig:
        return OtlpReceiverConfig(
            enabled=True, bearer_token=issued.token.get_secret_value()
        )

    receiver.app.dependency_overrides[get_receiver_config] = provide_config
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=receiver.app),
        base_url="http://collector",
    ) as client:
        headers = {"Authorization": f"Bearer {issued.token.get_secret_value()}"}
        assert (
            await client.post("/v1/logs", json={}, headers=headers)
        ).status_code == 200
        assert await receiver.service.revoke(receiver.caller, issued.metadata.token_id)
        assert (
            await client.post("/v1/logs", json={}, headers=headers)
        ).status_code == 401


@pytest.mark.asyncio
async def test_registry_failure_rejects_export_without_exposing_diagnostics(
    receiver: TokenReceiver,
) -> None:
    issued = await issue(
        receiver,
        TELEMETRY_TOKEN_AUDIENCE,
        (TELEMETRY_INGEST_SCOPE,),
        datetime.now(timezone.utc) + timedelta(hours=1),
    )
    install_telemetry_token_verifier(
        receiver.app,
        UnavailableTokenRuntime(receiver.runtime.database),
        AppConfig(),
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=receiver.app),
        base_url="http://collector",
    ) as client:
        response = await client.post(
            "/v1/logs",
            content="malformed",
            headers={"Authorization": f"Bearer {issued.token.get_secret_value()}"},
        )
    assert response.status_code == 503
    assert "private-database-information" not in response.text
    assert issued.token.get_secret_value() not in response.text


@pytest.mark.asyncio
async def test_receiver_without_authoritative_registry_refuses_personal_tokens(
    receiver: TokenReceiver,
) -> None:
    issued = await issue(
        receiver,
        TELEMETRY_TOKEN_AUDIENCE,
        (TELEMETRY_INGEST_SCOPE,),
        datetime.now(timezone.utc) + timedelta(hours=1),
    )
    app = FastAPI()
    install_telemetry_receiver(
        app,
        AppConfig(
            otlp_receiver=OtlpReceiverConfig(enabled=True, bearer_token="legacy-token"),
        ),
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://collector",
    ) as client:
        response = await client.post(
            "/v1/logs",
            json={},
            headers={"Authorization": f"Bearer {issued.token.get_secret_value()}"},
        )
    assert response.status_code == 401
