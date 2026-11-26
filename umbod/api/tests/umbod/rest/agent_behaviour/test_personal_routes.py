import json
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from time import time
from uuid import UUID, uuid4

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from tests.persistence_runtime import create_inmemory_runtime
from umbod.config import AppConfig
from umbod.core.agent_behaviour import PatternAssessment, PublishConfiguration, SubmitDiagnosticReport, create_agent_behaviour_service
from umbod.core.callers import LOCAL_DEVELOPMENT_ISSUER, AuthenticationProvenance, CallerContext, DeclaredIssuer, SubjectIdentity
from umbod.core.persistence import Database
from umbod.rest.authentication.verifiers import ProductionJwksJwtVerifier
from umbod.rest.factories import ConnectorApiDependencyFactories
from umbod.rest.main import create_app_with_dependency_factories

ISSUER = "https://reports.identity.test/"
PATH = "/api/me/agent-behaviour/reports"


@dataclass(frozen=True)
class ReportsApi:
    client: TestClient
    alice_headers: dict[str, str]
    bob_headers: dict[str, str]
    own_report: UUID
    other_user_report: UUID


@pytest.fixture(scope="module")
def signing_key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def headers(key: rsa.RSAPrivateKey, subject: str) -> dict[str, str]:
    token = jwt.encode(
        {"iss": ISSUER, "sub": subject, "aud": "api", "exp": int(time()) + 600, "groups": ["members"]},
        key, algorithm="RS256", headers={"kid": "reports-key"},
    )
    return {"Authorization": "Bearer " + token}


async def set_reporting(database: Database, enabled: bool) -> None:
    service = create_agent_behaviour_service(database)
    current = await service.get_configuration()
    await service.publish_configuration(PublishConfiguration(
        expected_revision=current.revision, reporting_enabled=enabled, patterns=current.patterns, playbooks=current.playbooks,
    ))


async def seed_report(
    database: Database, issuer: str, subject: str,
    authentication: AuthenticationProvenance = AuthenticationProvenance.UPSTREAM_VERIFIED,
) -> UUID:
    service = create_agent_behaviour_service(database)
    playbook = service.get_defaults().playbooks[0]
    instructions = await service.get_instructions(playbook.id)
    caller = CallerContext(authentication=authentication, subject=SubjectIdentity(
        issuer=DeclaredIssuer(value=issuer), subject=subject,
    ))
    submission = SubmitDiagnosticReport(
        idempotency_key=uuid4(),
        configuration_revision=instructions.configuration_revision,
        playbook_id=playbook.id,
        trigger="user_requested",
        assessments=tuple(
            PatternAssessment(pattern_id=pattern.id, status="not_observed", summary="", evidence=())
            for pattern in instructions.patterns
        ),
    )
    return (await service.submit_report(caller, submission)).report_id


@pytest.fixture
def api(signing_key: rsa.RSAPrivateKey, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[ReportsApi]:
    deployment = tmp_path / "connectors.json"
    deployment.write_text('{"connectors":[]}', encoding="utf-8")
    monkeypatch.setenv("UMBOD_CONNECTOR_DEPLOYMENT_CONFIGURATION_PATH", str(deployment))
    verifier = ProductionJwksJwtVerifier(ISSUER + "jwks", ISSUER, "api")
    jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(signing_key.public_key()))
    jwk["kid"] = "reports-key"
    cache = verifier.jwks_client.jwk_set_cache
    assert cache is not None
    cache.put({"keys": [jwk]})
    settings = AppConfig(
        rest={"metrics_enabled": False}, connector_store={"type": "inmemory"},
        admin_authentication={"mode": "jwt", "environment": "production", "jwks_url": ISSUER + "jwks"},
        oidc={"issuer_url": ISSUER, "audience": "api"},
    )
    runtime = create_inmemory_runtime()
    factories = ConnectorApiDependencyFactories.from_settings(settings, runtime, ())
    app = create_app_with_dependency_factories(factories, admin_verifier=verifier, user_verifier=verifier)
    with TestClient(app) as client:
        assert client.portal is not None
        client.portal.call(set_reporting, runtime.database, True)
        own_report = client.portal.call(seed_report, runtime.database, ISSUER, "alice")
        other_user_report = client.portal.call(seed_report, runtime.database, ISSUER, "bob")
        client.portal.call(seed_report, runtime.database, "https://another.identity.test/", "alice")
        client.portal.call(set_reporting, runtime.database, False)
        yield ReportsApi(client, headers(signing_key, "alice"), headers(signing_key, "bob"), own_report, other_user_report)


def test_default_local_rest_user_can_read_existing_mcp_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    deployment = tmp_path / "connectors.json"
    deployment.write_text('{"connectors":[]}', encoding="utf-8")
    monkeypatch.setenv("UMBOD_CONNECTOR_DEPLOYMENT_CONFIGURATION_PATH", str(deployment))
    settings = AppConfig(rest={"metrics_enabled": False}, connector_store={"type": "inmemory"})
    runtime = create_inmemory_runtime()
    factories = ConnectorApiDependencyFactories.from_settings(settings, runtime, ())
    with TestClient(create_app_with_dependency_factories(factories)) as client:
        assert client.portal is not None
        client.portal.call(set_reporting, runtime.database, True)
        report_id = str(client.portal.call(
            seed_report, runtime.database, LOCAL_DEVELOPMENT_ISSUER, "local-test-user", AuthenticationProvenance.LOCAL_TEST,
        ))

        listed = client.get(PATH)
        detail = client.get(f"{PATH}/{report_id}")

        assert listed.status_code == detail.status_code == 200
        assert [item["report_id"] for item in listed.json()["items"]] == [report_id]
        assert detail.json()["report_id"] == report_id


def test_personal_list_limits_count_and_page_to_verified_owner(api: ReportsApi) -> None:
    response = api.client.get(PATH, params={"limit": 1}, headers=api.alice_headers)

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json()["total"] == 1
    assert [item["report_id"] for item in response.json()["items"]] == [str(api.own_report)]
    assert api.client.get("/api/admin/agent-behaviour/reports", headers=api.alice_headers).status_code == 403


def test_personal_detail_returns_owned_snapshot_and_hides_foreign_report(api: ReportsApi) -> None:
    owned = api.client.get(f"{PATH}/{api.own_report}", headers=api.alice_headers)
    foreign = api.client.get(f"{PATH}/{api.own_report}", headers=api.bob_headers)
    missing = api.client.get(f"{PATH}/{uuid4()}", headers=api.bob_headers)

    assert owned.status_code == 200
    assert owned.json()["report_id"] == str(api.own_report)
    assert owned.headers["cache-control"] == "no-store"
    assert foreign.status_code == missing.status_code == 404
    assert foreign.json() == missing.json() == {"detail": {"code": "report_not_found"}}
    assert foreign.headers["cache-control"] == missing.headers["cache-control"] == "no-store"
    bob = api.client.get(f"{PATH}/{api.other_user_report}", headers=api.bob_headers)
    assert bob.status_code == 200


@pytest.mark.parametrize("path", [PATH, f"{PATH}/00000000-0000-0000-0000-000000000001"])
def test_personal_report_reads_reject_unauthenticated_owner_headers(api: ReportsApi, path: str) -> None:
    response = api.client.get(path, headers={"X-User-Id": "alice", "X-Issuer": ISSUER})

    assert response.status_code == 401
    assert response.headers["cache-control"] == "no-store"


def test_personal_report_schema_exposes_only_reads(api: ReportsApi) -> None:
    response = api.client.get("/api/me/openapi.json", headers=api.alice_headers)
    paths = response.json()["paths"]

    assert {path: set(methods) for path, methods in paths.items() if path.startswith("/agent-behaviour/")} == {
        "/agent-behaviour/reports": {"get"},
        "/agent-behaviour/reports/{report_id}": {"get"},
    }
