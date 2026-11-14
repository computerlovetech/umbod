from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import create_autospec
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.routing import Mount

from tests.persistence_runtime import create_inmemory_runtime
from umbod.config import AdminAuthConfig, AppConfig
from umbod.core.agent_behaviour import AgentBehaviourService, StorageUnavailable, SubmitDiagnosticReport, create_agent_behaviour_service
from umbod.core.callers import AuthenticationProvenance, CallerContext, DeclaredIssuer, SubjectIdentity
from umbod.core.persistence import Database
from umbod.rest.agent_behaviour import dependencies
from umbod.rest.agent_behaviour.dependencies import get_agent_behaviour_service
from umbod.rest.factories import ConnectorApiDependencyFactories
from umbod.rest.main import create_app, create_app_with_dependency_factories

PATH = "/api/admin/agent-behaviour"


@dataclass(frozen=True)
class BehaviourApi:
    client: TestClient
    admin: FastAPI
    service: AgentBehaviourService


@pytest.fixture
def settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AppConfig:
    deployment = tmp_path / "deployment.json"
    deployment.write_text('{"connectors": []}', encoding="utf-8")
    monkeypatch.setenv("UMBOD_CONNECTOR_DEPLOYMENT_CONFIGURATION_PATH", str(deployment))
    return AppConfig(rest={"metrics_enabled": False}, connector_store={"type": "inmemory"}, admin_authentication={"mode": "simulation", "simulated_admin": True})


@pytest.fixture
def api(settings: AppConfig) -> Iterator[BehaviourApi]:
    runtime = create_inmemory_runtime()
    factories = ConnectorApiDependencyFactories.from_settings(settings, runtime, ())
    root = create_app_with_dependency_factories(factories)
    admin = next(route.app for route in root.routes if isinstance(route, Mount) and route.path == "/api/admin")
    assert isinstance(admin, FastAPI)
    with TestClient(root, raise_server_exceptions=False) as client:
        yield BehaviourApi(client, admin, create_agent_behaviour_service(runtime.database))


def publication() -> dict[str, object]:
    return {
        "expected_revision": 1,
        "patterns": [{"id": identifier, "name": identifier, "description": "Description", "assessment_prompt": "Assess facts", "inclusion_criteria": "Include", "exclusion_criteria": "Exclude", "categories": ["quality"], "polarity": "neutral", "enabled": True} for identifier in ("fallback", "verification", "unassessed")],
        "playbooks": [{"id": "review", "name": "Review", "collection_instructions": "Collect authorized facts", "pattern_ids": ["fallback", "verification", "unassessed"], "enabled": True, "allow_proactive": False}],
    }


def seed_report(api: BehaviourApi) -> str:
    response = api.client.put(PATH + "/configuration", json=publication())
    assert response.status_code == 200
    command = SubmitDiagnosticReport.model_validate({
        "idempotency_key": str(uuid4()), "configuration_revision": 2, "playbook_id": "review", "trigger": "user_requested",
        "assessments": [
            {"pattern_id": "fallback", "status": "observed", "summary": "Fallback used", "evidence": ["<script>unsafe()</script>"]},
            {"pattern_id": "verification", "status": "not_observed", "summary": "", "evidence": []},
            {"pattern_id": "unassessed", "status": "not_assessed", "summary": "Context unavailable", "evidence": []},
        ],
    })
    caller = CallerContext(authentication=AuthenticationProvenance.UPSTREAM_VERIFIED, subject=SubjectIdentity(issuer=DeclaredIssuer(value="https://identity.test"), subject="agent"))
    receipt = api.client.portal.call(api.service.submit_report, caller, command)
    return str(receipt.report_id)


def test_initial_configuration_and_atomic_publication_conflict(api: BehaviourApi) -> None:
    initial = api.client.get(PATH + "/configuration")
    assert initial.status_code == 200
    assert initial.json() == api.service.get_defaults().model_dump(mode="json")
    assert initial.headers["cache-control"] == "no-store"
    saved = api.client.put(PATH + "/configuration", json=publication())
    assert saved.status_code == 200
    assert saved.json()["revision"] == 2
    assert saved.headers["cache-control"] == "no-store"
    conflict = api.client.put(PATH + "/configuration", json=publication())
    assert conflict.status_code == 409
    assert conflict.json()["detail"] == {"code": "revision_conflict", "current": saved.json()}
    assert conflict.headers["cache-control"] == "no-store"
    assert api.client.get(PATH + "/configuration").json() == saved.json()


def test_defaults_catalog_is_non_cacheable_and_does_not_replace_saved_configuration(api: BehaviourApi) -> None:
    catalog = api.client.get(PATH + "/defaults")
    assert catalog.status_code == 200
    assert catalog.headers["cache-control"] == "no-store"
    assert catalog.json() == api.service.get_defaults().model_dump(mode="json")
    saved = api.client.put(PATH + "/configuration", json=publication())
    assert saved.status_code == 200
    repeated = api.client.get(PATH + "/defaults")
    assert repeated.status_code == 200
    assert repeated.headers["cache-control"] == "no-store"
    assert repeated.json() == catalog.json()
    assert api.client.get(PATH + "/configuration").json() == saved.json()


def test_defaults_catalog_preserves_intentionally_empty_saved_configuration(api: BehaviourApi) -> None:
    saved = api.client.put(PATH + "/configuration", json={"expected_revision": 1, "patterns": [], "playbooks": []})
    assert saved.status_code == 200
    assert len(api.client.get(PATH + "/defaults").json()["patterns"]) == 4
    assert api.client.get(PATH + "/configuration").json() == saved.json()
    assert saved.json() == {"revision": 2, "patterns": [], "playbooks": []}


def test_identical_successful_save_increments_revision(api: BehaviourApi) -> None:
    payload = {"expected_revision": 1, "patterns": [], "playbooks": []}
    assert api.client.put(PATH + "/configuration", json=payload).json()["revision"] == 2
    payload["expected_revision"] = 2
    response = api.client.put(PATH + "/configuration", json=payload)
    assert response.status_code == 200
    assert response.json()["revision"] == 3


def test_invalid_dependency_rejects_entire_publication(api: BehaviourApi) -> None:
    payload = publication()
    payload["patterns"] = []
    response = api.client.put(PATH + "/configuration", json=payload)
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "configuration_invalid"
    assert response.json()["detail"]["issues"]
    assert response.headers["cache-control"] == "no-store"
    assert api.client.get(PATH + "/configuration").json()["revision"] == 1


@pytest.mark.parametrize("query", ["limit=0", "limit=101", "offset=-1", "status=unknown", "pattern_id=Bad", "playbook_id=", "unexpected=secret", "limit=1.5"])
def test_report_query_is_strict_and_errors_do_not_echo_values(api: BehaviourApi, query: str) -> None:
    response = api.client.get(PATH + "/reports?" + query)
    assert response.status_code == 422
    assert response.headers["cache-control"] == "no-store"
    assert "secret" not in response.text
    assert "input" not in response.text


@pytest.mark.parametrize("query,total", [("", 1), ("playbook_id=review", 1), ("playbook_id=other", 0), ("pattern_id=fallback&status=observed", 1), ("pattern_id=verification&status=observed", 0), ("status=not_assessed", 1), ("limit=1&offset=1", 1)])
def test_reports_filter_same_assessment_and_count_before_pagination(api: BehaviourApi, query: str, total: int) -> None:
    report_id = seed_report(api)
    response = api.client.get(PATH + "/reports?" + query)
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json()["total"] == total
    if total and "offset=1" not in query:
        assert response.json()["items"][0]["report_id"] == report_id
        assert response.json()["items"][0]["observed_pattern_ids"] == ["fallback"]
    else:
        assert response.json()["items"] == []


def test_report_detail_returns_original_snapshot_and_all_statuses(api: BehaviourApi) -> None:
    report_id = seed_report(api)
    changed = api.client.put(PATH + "/configuration", json={"expected_revision": 2, "patterns": [], "playbooks": []})
    assert changed.status_code == 200
    assert changed.json()["revision"] == 3
    response = api.client.get(PATH + "/reports/" + report_id)
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    report = response.json()
    assert report["instructions"]["configuration_revision"] == 2
    assert report["instructions"]["playbook"]["collection_instructions"] == "Collect authorized facts"
    assert report["instructions"]["patterns"][0]["assessment_prompt"] == "Assess facts"
    assert [item["status"] for item in report["submission"]["assessments"]] == ["observed", "not_observed", "not_assessed"]
    assert report["submission"]["assessments"][0]["evidence"] == ["<script>unsafe()</script>"]
    assert report["caller"]["subject"]["subject"] == "agent"


def test_delete_is_idempotent_and_removes_detail_and_list(api: BehaviourApi) -> None:
    report_id = seed_report(api)
    for _ in range(2):
        response = api.client.delete(PATH + "/reports/" + report_id)
        assert response.status_code == 204
        assert response.content == b""
        assert response.headers["cache-control"] == "no-store"
    missing = api.client.get(PATH + "/reports/" + report_id)
    assert missing.status_code == 404
    assert missing.headers["cache-control"] == "no-store"
    assert api.client.get(PATH + "/reports").json() == {"items": [], "total": 0}


@pytest.mark.parametrize("method", ["GET", "DELETE"])
def test_missing_report_detail_and_deletion(api: BehaviourApi, method: str) -> None:
    response = api.client.request(method, PATH + "/reports/" + str(uuid4()))
    assert response.status_code == (404 if method == "GET" else 204)
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize("path", ["/defaults", "/configuration", "/reports", "/reports/00000000-0000-0000-0000-000000000001"])
@pytest.mark.parametrize("authentication,status", [(AdminAuthConfig(mode="jwt"), 401), (AdminAuthConfig(mode="simulation", simulated_admin=False), 403)])
def test_existing_admin_boundary_denies_direct_access(settings: AppConfig, path: str, authentication: AdminAuthConfig, status: int) -> None:
    denied_settings = settings.model_copy(update={"admin_authentication": authentication})
    with TestClient(create_app(denied_settings, [])) as client:
        response = client.get(PATH + path)
    assert response.status_code == status
    assert response.headers["cache-control"] == "no-store"
    assert "patterns" not in response.text


@pytest.mark.parametrize("payload", [
    {"expected_revision": 1, "patterns": [], "playbooks": [], "private-extra-field": "private-value"},
    {"expected_revision": -1, "patterns": [], "playbooks": []},
    {"expected_revision": 1, "patterns": [{"id": "Invalid", "description": "private-value"}], "playbooks": []},
])
def test_invalid_publication_has_bounded_safe_field_issues(api: BehaviourApi, payload: dict[str, object]) -> None:
    response = api.client.put(PATH + "/configuration", json=payload)
    assert response.status_code == 422
    assert response.headers["cache-control"] == "no-store"
    assert "private-value" not in response.text
    assert "private-extra-field" not in response.text
    assert 1 <= len(response.json()["detail"]["issues"]) <= 50
    assert api.client.get(PATH + "/configuration").json()["revision"] == 1


@pytest.mark.parametrize("method", ["GET", "DELETE"])
def test_invalid_report_identifier_is_non_cacheable(api: BehaviourApi, method: str) -> None:
    response = api.client.request(method, PATH + "/reports/not-a-uuid")
    assert response.status_code == 422
    assert response.headers["cache-control"] == "no-store"
    assert "not-a-uuid" not in response.text


def test_cookie_csrf_prevents_publication(api: BehaviourApi) -> None:
    response = api.client.put(PATH + "/configuration", json=publication(), headers={"Cookie": "gateway=yes"})
    assert response.status_code == 403
    assert response.headers["cache-control"] == "no-store"
    assert api.client.get(PATH + "/configuration").json()["revision"] == 1
    accepted = api.client.put(PATH + "/configuration", json=publication(), headers={"Cookie": "gateway=yes", "Origin": "http://localhost:3010", "X-Umbod-Web-Request": "1"})
    assert accepted.status_code == 200


@pytest.mark.parametrize("failure,status", [(StorageUnavailable(), 503), (RuntimeError("private database credentials"), 500)])
def test_storage_failures_are_safe_and_non_cacheable(api: BehaviourApi, failure: Exception, status: int) -> None:
    service = create_autospec(AgentBehaviourService, instance=True)
    service.get_configuration.side_effect = failure

    def provide_service() -> AgentBehaviourService:
        return service

    api.admin.dependency_overrides[get_agent_behaviour_service] = provide_service
    response = api.client.get(PATH + "/configuration")
    assert response.status_code == status
    assert response.headers["cache-control"] == "no-store"
    assert "private" not in response.text


@pytest.mark.parametrize("path", ["/configuration", "/defaults"])
def test_request_services_share_only_the_existing_database(api: BehaviourApi, monkeypatch: pytest.MonkeyPatch, path: str) -> None:
    factory = dependencies.create_agent_behaviour_service
    services: list[AgentBehaviourService] = []
    databases: list[Database] = []

    def track(database: Database) -> AgentBehaviourService:
        service = factory(database)
        services.append(service)
        databases.append(database)
        return service

    monkeypatch.setattr(dependencies, "create_agent_behaviour_service", track)
    assert api.client.get(PATH + path).status_code == 200
    assert api.client.get(PATH + path).status_code == 200
    assert services[0] is not services[1]
    assert databases[0] is databases[1]


def test_no_rest_submission_endpoint_is_published(api: BehaviourApi) -> None:
    response = api.client.post(PATH + "/reports", json={})
    assert response.status_code == 405
    assert response.headers["cache-control"] == "no-store"
    schema = api.client.get("/api/admin/openapi.json").json()
    assert set(schema["paths"]["/agent-behaviour/reports"]) == {"get"}
