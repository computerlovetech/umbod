from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from tests.persistence_runtime import create_inmemory_runtime

from umbod.config import AppConfig, OtlpReceiverConfig
from umbod.core.telemetry import TelemetryExport, TelemetrySink
from umbod.core.persistence import PersistenceRuntime
from umbod.rest.factories import ConnectorApiDependencyFactories
from umbod.rest.main import create_app_with_dependency_factories
from umbod.rest.telemetry import install_telemetry_receiver
from umbod.rest.telemetry.dependencies import get_telemetry_sink
from umbod.rest.telemetry.token_authentication import (
    DatabaseTelemetryTokenVerifier,
    TelemetryPersonalAccessTokenVerifier,
    get_telemetry_token_verifier,
    install_telemetry_token_verifier,
)

from .test_application_boundary import URL, body


class AcceptedTelemetrySink:
    def export(self, batch: TelemetryExport) -> None:
        pass


def accepted_sink() -> TelemetrySink:
    return AcceptedTelemetrySink()


@dataclass(frozen=True)
class LocalApi:
    user: TestClient
    collector: TestClient
    collector_app: FastAPI
    runtime: PersistenceRuntime
    settings: AppConfig


@pytest.fixture
def local_api(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[LocalApi]:
    deployment = tmp_path / "connectors.json"
    deployment.write_text('{"connectors":[]}', encoding="utf-8")
    monkeypatch.setenv("UMBOD_CONNECTOR_DEPLOYMENT_CONFIGURATION_PATH", str(deployment))
    settings = AppConfig(
        runtime={"profile": "local", "auth": "dev"},
        rest={"metrics_enabled": False},
        connector_store={"type": "inmemory"},
        admin_authentication={
            "mode": "simulation",
            "environment": "development",
            "simulated_user_id": "local-pat-user",
        },
        otlp_receiver=OtlpReceiverConfig(enabled=True, bearer_token="legacy-token"),
    )
    runtime = create_inmemory_runtime()
    factories = ConnectorApiDependencyFactories.from_settings(settings, runtime, ())
    app = create_app_with_dependency_factories(factories)
    collector = FastAPI()
    install_telemetry_receiver(collector, settings)
    install_telemetry_token_verifier(collector, runtime, settings)
    collector.dependency_overrides[get_telemetry_sink] = accepted_sink
    with TestClient(app) as user, TestClient(collector) as ingestion:
        yield LocalApi(
            user=user, collector=ingestion, collector_app=collector, runtime=runtime, settings=settings
        )


def test_local_workspace_user_can_create_and_list_real_personal_tokens(local_api: LocalApi) -> None:
    created = local_api.user.post(URL, json=body())
    assert created.status_code == 201
    data = created.json()
    assert data["metadata"]["owner"] == {
        "issuer": "urn:umbod:local",
        "subject": "local-pat-user",
    }
    listed = local_api.user.get(URL)
    assert listed.status_code == 200
    assert listed.json() == [data["metadata"]]
    assert data["token"] not in listed.text
    assert "digest" not in listed.text


@pytest.mark.parametrize("signal", ["logs", "metrics", "traces"])
def test_local_token_authenticates_collector_and_revocation_is_immediate(
    local_api: LocalApi, signal: str
) -> None:
    created = local_api.user.post(URL, json=body())
    assert created.status_code == 201
    data = created.json()
    headers = {"Authorization": "Bearer " + data["token"]}
    accepted = local_api.collector.post("/v1/" + signal, json={}, headers=headers)
    assert accepted.status_code == 200, accepted.text
    revoked = local_api.user.delete(URL + "/" + data["metadata"]["token_id"])
    assert revoked.status_code == 204
    assert local_api.collector.post("/v1/" + signal, json={}, headers=headers).status_code == 401
    assert local_api.user.get(URL).json() == []
    assert local_api.user.delete(URL + "/" + data["metadata"]["token_id"]).status_code == 404


@pytest.mark.parametrize(
    "section,field,value",
    [
        ("runtime", "profile", "production"),
        ("runtime", "auth", "oidc"),
        ("admin_authentication", "mode", "jwt"),
        ("admin_authentication", "environment", "production"),
        ("admin_authentication", "simulated_user_id", " "),
    ],
)
def test_local_tokens_in_reused_registry_are_denied_outside_full_local_gate(
    local_api: LocalApi, section: str, field: str, value: str
) -> None:
    created = local_api.user.post(URL, json=body())
    assert created.status_code == 201
    headers = {"Authorization": "Bearer " + created.json()["token"]}
    assert local_api.collector.post("/v1/logs", json={}, headers=headers).status_code == 200
    changed_section = getattr(local_api.settings, section).model_copy(update={field: value})
    changed_settings = local_api.settings.model_copy(update={section: changed_section})
    install_telemetry_token_verifier(
        local_api.collector_app, local_api.runtime, changed_settings
    )
    denied = local_api.collector.post("/v1/logs", json={}, headers=headers)
    assert denied.status_code == 401
    install_telemetry_token_verifier(
        local_api.collector_app, local_api.runtime, local_api.settings
    )
    assert local_api.collector.post("/v1/logs", json={}, headers=headers).status_code == 200


def test_collector_verifier_with_local_tokens_disabled_denies_local_namespace_tokens(
    local_api: LocalApi,
) -> None:
    created = local_api.user.post(URL, json=body())
    assert created.status_code == 201
    def default_verifier() -> TelemetryPersonalAccessTokenVerifier:
        return DatabaseTelemetryTokenVerifier(local_api.runtime, False)

    local_api.collector_app.dependency_overrides[get_telemetry_token_verifier] = default_verifier
    denied = local_api.collector.post(
        "/v1/logs", json={},
        headers={"Authorization": "Bearer " + created.json()["token"]},
    )
    assert denied.status_code == 401
