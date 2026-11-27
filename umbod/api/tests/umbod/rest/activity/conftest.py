import json
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from time import time
from uuid import uuid4

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.routing import Mount

from tests.persistence_runtime import create_inmemory_runtime
from tests.support.telemetry_runtime import InMemoryTelemetryAnalyticsRuntime
from umbod.config import AppConfig
from umbod.core.activity.models import (
    AfterSession, HarnessOutcomes, HarnessSummary, MissingSession, SessionDetailQuery, SessionKey,
    SessionListQuery, SessionReport, SessionSlice, SessionSummary,
)
from umbod.core.activity.ports import HarnessActivityReader
from umbod.core.callers import AuthenticationProvenance, CallerContext, DeclaredIssuer, SubjectIdentity
from umbod.core.persistence import PersistenceRuntime
from umbod.core.telemetry.analytics import OwnedLog, TelemetryAnalyticsRuntime, TimeRange, analytics_owner_id
from umbod.core.usage import UsageBatch, UsageKind, UsageOutcome, UsageOwner, UsageRecord, UsageTool, resolve_usage_owner
from umbod.core.usage.models import BuiltinUsageToolTarget, UnavailableUsageTool
from umbod.core.usage.store import DatabaseUsageStore
from umbod.infrastructure import create_disabled_analytics_runtime, create_rest_metrics_recorder
from umbod.rest.activity.deps import get_activity_clock
from umbod.rest.authentication.verifiers import ProductionJwksJwtVerifier
from umbod.rest.main import create_app_with_shared_persistence

ISSUER = "https://activity.identity.test/"
NOW = datetime(2026, 11, 12, 12, tzinfo=timezone.utc)
BASE = "/api/me/activity"
SESSIONS = BASE + "/sessions"
DETAIL = SESSIONS + "/codex/alice%2Fsegment"


@dataclass(frozen=True)
class ActivityApi:
    client: TestClient
    personal_app: FastAPI
    signing_key: rsa.RSAPrivateKey
    settings: AppConfig
    persistence: PersistenceRuntime

    def headers(
        self, subject: str, issuer: str = ISSUER, groups: tuple[str, ...] = ("members",),
    ) -> dict[str, str]:
        token = jwt.encode(
            {"iss": issuer, "sub": subject, "aud": "api", "exp": int(time()) + 600, "groups": groups},
            self.signing_key, algorithm="RS256", headers={"kid": "activity-key"},
        )
        return {"Authorization": "Bearer " + token}


@pytest.fixture(scope="module")
def signing_key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture
def settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AppConfig:
    deployment = tmp_path / "deployment.json"
    deployment.write_text('{"connectors":[]}', encoding="utf-8")
    monkeypatch.setenv("UMBOD_CONNECTOR_DEPLOYMENT_CONFIGURATION_PATH", str(deployment))
    return AppConfig(
        rest={"metrics_enabled": False},
        connector_store={"type": "inmemory"},
        admin_authentication={"mode": "jwt", "environment": "production", "jwks_url": ISSUER + "jwks"},
        oidc={"issuer_url": ISSUER, "audience": "api"},
    )


def _verifier(key: rsa.RSAPrivateKey) -> ProductionJwksJwtVerifier:
    verifier = ProductionJwksJwtVerifier(ISSUER + "jwks", ISSUER, "api")
    jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key()))
    jwk["kid"] = "activity-key"
    cache = verifier.jwks_client.jwk_set_cache
    assert cache is not None
    cache.put({"keys": [jwk]})
    return verifier


def _usage_record(subject: str, kind: UsageKind, outcome: UsageOutcome, occurred_at: datetime) -> UsageRecord:
    owner = resolve_usage_owner(CallerContext(
        authentication=AuthenticationProvenance.UPSTREAM_VERIFIED,
        subject=SubjectIdentity(issuer=DeclaredIssuer(value=ISSUER), subject=subject),
    ))
    assert isinstance(owner, UsageOwner)
    unix_nanos = int(occurred_at.timestamp()) * 1_000_000_000
    return UsageRecord(
        event_id=uuid4(), owner_id=owner.owner_id, occurred_at_unix_nano=unix_nanos,
        observed_at_unix_nano=unix_nanos, kind=kind, outcome=outcome,
        duration_ms=1.0, service_name="umbod-mcp", trace_id="", span_id="",
        tool=UsageTool(
            target=BuiltinUsageToolTarget(kind="builtin", registered_name="files"),
            tool_name="Files", connector_name="Umbod",
        ) if kind == UsageKind.TOOL else UnavailableUsageTool(kind="unavailable"),
    )


async def _seed_usage(persistence: PersistenceRuntime) -> None:
    await DatabaseUsageStore(persistence.database).append_usage(UsageBatch(records=(
        _usage_record("alice", UsageKind.TOOL, UsageOutcome.SUCCESS, NOW),
        _usage_record("alice", UsageKind.TOOL, UsageOutcome.SUCCESS, NOW - timedelta(days=10)),
        _usage_record("alice", UsageKind.RESOURCE, UsageOutcome.FAILURE, NOW),
        _usage_record("alice", UsageKind.PROMPT, UsageOutcome.CANCELLED, NOW),
        _usage_record("bob", UsageKind.TOOL, UsageOutcome.FAILURE, NOW),
    )))


def _session(session_id: str, age: timedelta, outcomes: HarnessOutcomes) -> SessionSummary:
    timestamp = NOW - age
    return SessionSummary(
        key=SessionKey(source="codex", session_id=session_id),
        first_seen_at=timestamp, last_seen_at=timestamp, outcomes=outcomes,
    )


class FixtureHarnessActivityReader:
    def __init__(self) -> None:
        success = HarnessOutcomes(success=1, failure=0, unknown=0)
        failure = HarnessOutcomes(success=0, failure=1, unknown=0)
        self._sessions = {
            analytics_owner_id(ISSUER, "alice"): (
                _session("alice/segment", timedelta(minutes=1), success),
                _session("alice-second", timedelta(minutes=2), success),
            ),
            analytics_owner_id(ISSUER, "bob"): (
                _session("bob-private", timedelta(minutes=1), failure),
            ),
        }

    async def summarize(self, owner: OwnedLog, window: TimeRange) -> HarnessSummary:
        sessions = self._sessions.get(owner.owner_id, ())
        return HarnessSummary(
            outcomes=HarnessOutcomes(
                success=sum(session.outcomes.success for session in sessions),
                failure=sum(session.outcomes.failure for session in sessions),
                unknown=0,
            ),
            top_tools=(), skill_activations=0,
        )

    async def list_sessions(self, query: SessionListQuery) -> SessionSlice:
        sessions = tuple(
            session for session in self._sessions.get(query.owner.owner_id, ())
            if query.search in session.key.session_id
        )
        if isinstance(query.start, AfterSession):
            sessions = tuple(session for session in sessions if session.last_seen_at < query.start.position.last_seen_at)
        return SessionSlice(sessions=sessions[:query.limit], has_more=len(sessions) > query.limit)

    async def get_session(self, query: SessionDetailQuery) -> SessionReport | MissingSession:
        for session in self._sessions.get(query.owner.owner_id, ()):
            if session.key == query.key:
                return SessionReport(
                    session=session, top_tools=(), failed_tools=(), has_more_failed_tools=False, skill_activations=0,
                )
        return MissingSession(kind="missing")


class ActivityAnalyticsRuntime(InMemoryTelemetryAnalyticsRuntime):
    def create_harness_activity_reader(self) -> HarnessActivityReader:
        return FixtureHarnessActivityReader()


def _clock() -> datetime:
    return NOW


def _provide_clock() -> Callable[[], datetime]:
    return _clock


@contextmanager
def _mounted_activity_api(
    settings: AppConfig, signing_key: rsa.RSAPrivateKey, persistence: PersistenceRuntime, analytics: TelemetryAnalyticsRuntime,
) -> Iterator[ActivityApi]:
    verifier = _verifier(signing_key)
    root = create_app_with_shared_persistence(
        persistence, analytics, create_rest_metrics_recorder(), settings, (),
        admin_verifier=verifier, user_verifier=verifier,
    )
    personal = next(route.app for route in root.routes if isinstance(route, Mount) and route.path == "/api/me")
    assert isinstance(personal, FastAPI)
    personal.dependency_overrides[get_activity_clock] = _provide_clock

    with TestClient(root) as client:
        assert client.portal is not None
        try:
            client.portal.call(_seed_usage, persistence)
            yield ActivityApi(client, personal, signing_key, settings, persistence)
        finally:
            client.portal.call(analytics.shutdown)
            client.portal.call(persistence.shutdown)


@pytest.fixture
def api(settings: AppConfig, signing_key: rsa.RSAPrivateKey) -> Iterator[ActivityApi]:
    persistence = create_inmemory_runtime()
    analytics = ActivityAnalyticsRuntime(persistence.database, persistence.readiness)
    with _mounted_activity_api(settings, signing_key, persistence, analytics) as activity_api:
        yield activity_api


@pytest.fixture
def disabled_harness_api(settings: AppConfig, signing_key: rsa.RSAPrivateKey) -> Iterator[ActivityApi]:
    with _mounted_activity_api(
        settings, signing_key, create_inmemory_runtime(), create_disabled_analytics_runtime(),
    ) as activity_api:
        yield activity_api
