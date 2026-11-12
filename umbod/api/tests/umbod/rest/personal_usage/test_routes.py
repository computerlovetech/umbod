import json
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import datetime, timezone
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
from umbod.config import AppConfig
from umbod.core.callers import AuthenticationProvenance, CallerContext, DeclaredIssuer, SubjectIdentity
from umbod.core.persistence import Database
from umbod.core.usage import OwnedUsageQuery, UsageBatch, UsageKind, UsageOutcome, UsageOwner, UsageReader, UsageRecord, UsageSummary, resolve_usage_owner
from umbod.core.usage.store import DatabaseUsageStore
from umbod.rest.authentication.verifiers import ProductionJwksJwtVerifier
from umbod.rest.factories import ConnectorApiDependencyFactories
from umbod.rest.main import create_app_with_dependency_factories
from umbod.rest.personal_usage.deps import get_usage_clock, get_usage_reader
from umbod.rest.personal_usage.models import PersonalUsageResponse


ISSUER = 'https://usage.identity.test/'
NOW = datetime(2026, 11, 12, 12, tzinfo=timezone.utc)


@dataclass(frozen=True)
class UsageApi:
    client: TestClient
    personal_app: FastAPI
    alice: str
    bob: str
    signing_key: rsa.RSAPrivateKey
    settings: AppConfig


@pytest.fixture(scope='module')
def signing_key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def signed_token(key: rsa.RSAPrivateKey, subject: str, issuer: str) -> str:
    return jwt.encode(
        {'iss': issuer, 'sub': subject, 'aud': 'api', 'exp': int(time()) + 600, 'groups': ['members']},
        key, algorithm='RS256', headers={'kid': 'usage-key'},
    )


def owner_id(subject: str) -> str:
    owner = resolve_usage_owner(CallerContext(
        authentication=AuthenticationProvenance.UPSTREAM_VERIFIED,
        subject=SubjectIdentity(issuer=DeclaredIssuer(value=ISSUER), subject=subject),
    ))
    assert isinstance(owner, UsageOwner)
    return owner.owner_id


def usage_record(subject: str, kind: UsageKind, outcome: UsageOutcome) -> UsageRecord:
    return UsageRecord(
        event_id=uuid4(), owner_id=owner_id(subject),
        occurred_at_unix_nano=int(NOW.timestamp()) * 1_000_000_000,
        observed_at_unix_nano=int(NOW.timestamp()) * 1_000_000_000,
        kind=kind, outcome=outcome, duration_ms=1.0, service_name='umbod-mcp', trace_id='', span_id='',
    )


async def seed_usage(database: Database) -> None:
    await DatabaseUsageStore(database).append_usage(UsageBatch(records=(
        usage_record('alice', UsageKind.TOOL, UsageOutcome.SUCCESS),
        usage_record('alice', UsageKind.TOOL, UsageOutcome.SUCCESS),
        usage_record('alice', UsageKind.RESOURCE, UsageOutcome.FAILURE),
        usage_record('alice', UsageKind.PROMPT, UsageOutcome.CANCELLED),
        usage_record('bob', UsageKind.TOOL, UsageOutcome.FAILURE),
    )))


def fixed_clock() -> datetime:
    return NOW


@pytest.fixture
def api(signing_key: rsa.RSAPrivateKey, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[UsageApi]:
    deployment = tmp_path / 'connectors.json'
    deployment.write_text('{"connectors":[]}', encoding='utf-8')
    monkeypatch.setenv('UMBOD_CONNECTOR_DEPLOYMENT_CONFIGURATION_PATH', str(deployment))
    verifier = ProductionJwksJwtVerifier(ISSUER + 'jwks', ISSUER, 'api')
    key = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(signing_key.public_key()))
    key['kid'] = 'usage-key'
    cache = verifier.jwks_client.jwk_set_cache
    assert cache is not None
    cache.put({'keys': [key]})
    settings = AppConfig(
        rest={'metrics_enabled': False}, connector_store={'type': 'inmemory'},
        admin_authentication={'mode': 'jwt', 'environment': 'production', 'jwks_url': ISSUER + 'jwks'},
        oidc={'issuer_url': ISSUER, 'audience': 'api'},
    )
    runtime = create_inmemory_runtime()
    factories = ConnectorApiDependencyFactories.from_settings(settings, runtime, ())
    root = create_app_with_dependency_factories(factories, admin_verifier=verifier, user_verifier=verifier)
    personal = next(route.app for route in root.routes if isinstance(route, Mount) and route.path == '/api/me')
    assert isinstance(personal, FastAPI)

    def provide_clock() -> Callable[[], datetime]:
        return fixed_clock

    personal.dependency_overrides[get_usage_clock] = provide_clock
    with TestClient(root) as client:
        client.portal.call(seed_usage, runtime.database)
        yield UsageApi(client, personal, signed_token(signing_key, 'alice', ISSUER), signed_token(signing_key, 'bob', ISSUER), signing_key, settings)


def test_normal_user_reads_only_own_persisted_usage_without_administrator_access(api: UsageApi) -> None:
    alice = api.client.get('/api/me/usage', headers={'Authorization': 'Bearer ' + api.alice})
    bob = api.client.get('/api/me/usage', headers={'Authorization': 'Bearer ' + api.bob})

    assert alice.status_code == 200
    assert bob.status_code == 200
    assert alice.headers['cache-control'] == 'no-store'
    summary = PersonalUsageResponse.model_validate(alice.json())
    other = PersonalUsageResponse.model_validate(bob.json())
    assert summary.totals.tool.success == 2
    assert summary.totals.resource.failure == 1
    assert summary.totals.prompt.cancelled == 1
    assert summary.totals.tool.failure == 0
    assert other.totals.tool.failure == 1
    assert other.totals.total == 1
    assert summary.identity_key != other.identity_key
    assert len(summary.daily) == 7
    assert summary.daily[-1].counts == summary.totals
    assert all(day.counts.total == 0 for day in summary.daily[:-1])
    assert api.client.get('/api/admin/overview', headers={'Authorization': 'Bearer ' + api.alice}).status_code == 403


@pytest.mark.parametrize('days', [7, 30])
def test_supported_window_has_exact_zero_filled_utc_dates(api: UsageApi, days: int) -> None:
    response = api.client.get('/api/me/usage', params={'days': days}, headers={'Authorization': 'Bearer ' + api.alice})

    assert response.status_code == 200
    summary = PersonalUsageResponse.model_validate(response.json())
    assert len(summary.daily) == days
    assert summary.range.timezone == 'UTC'
    assert (summary.range.end - summary.range.start).days == days
    assert summary.as_of == NOW


@pytest.mark.parametrize('query', [
    {'days': '0'}, {'days': '8'}, {'days': '31'}, {'days': 'invalid'},
    {'owner': 'bob'}, {'owner_id': 'b' * 64}, {'scope': 'instance'}, {'user': 'bob'},
])
def test_invalid_or_owner_selecting_queries_are_rejected(api: UsageApi, query: dict[str, str]) -> None:
    response = api.client.get('/api/me/usage', params=query, headers={'Authorization': 'Bearer ' + api.alice})

    assert response.status_code == 422
    assert response.headers['cache-control'] == 'no-store'


def test_unauthenticated_and_wrong_issuer_requests_are_rejected(api: UsageApi) -> None:
    assert api.client.get('/api/me/usage').status_code == 401
    wrong = signed_token(api.signing_key, 'alice', 'https://other-issuer.test/')
    rejected = api.client.get('/api/me/usage', headers={'Authorization': 'Bearer ' + wrong})
    assert rejected.status_code == 401
    assert rejected.headers['cache-control'] == 'no-store'


def test_unresolved_verified_subject_does_not_fall_back_to_global_counts(api: UsageApi) -> None:
    token = signed_token(api.signing_key, '', ISSUER)
    response = api.client.get('/api/me/usage', headers={'Authorization': 'Bearer ' + token})

    assert response.status_code == 403
    assert 'totals' not in response.json()


def test_disabled_collection_is_unavailable_instead_of_empty(api: UsageApi) -> None:
    api.settings.personal_usage.enabled = False
    response = api.client.get('/api/me/usage', headers={'Authorization': 'Bearer ' + api.alice})

    assert response.status_code == 503
    assert response.headers['cache-control'] == 'no-store'
    assert 'totals' not in response.json()


class UnavailableReader:
    async def count_usage(self, query: OwnedUsageQuery) -> UsageSummary:
        raise RuntimeError('private-storage-error')


def test_unavailable_persistence_is_not_reported_as_zero_usage(api: UsageApi) -> None:
    def unavailable_reader() -> UsageReader:
        return UnavailableReader()

    api.personal_app.dependency_overrides[get_usage_reader] = unavailable_reader
    response = api.client.get('/api/me/usage', headers={'Authorization': 'Bearer ' + api.alice})

    assert response.status_code == 503
    assert response.headers['cache-control'] == 'no-store'
    assert 'private-storage-error' not in response.text
    assert 'totals' not in response.json()
